"""오케스트레이터 — ID 기반 누적 관리.

jobs.csv  : 사람인 rec_idx(id)로 누적. 이번 스크래핑에 잡히면 status=모집중,
            안 잡힌 기존 공고는 삭제하지 않고 status=마감으로 표시(찜 기록 보존).
companies.csv : 회사 csn(id)로 누적. 새 회사만(또는 오래된 회사) 기업정보+매출액 조회.

실행:
  python3 build_csv.py
환경변수(선택):
  DART_API_KEY  매출액 보강용 DART 키
  COMPANY_REFRESH_DAYS  회사정보 재조회 주기(기본 30일)
"""
import csv
import os
import re
import datetime

from config import JOB_COLUMNS, COMPANY_COLUMNS, OUT_JOBS, OUT_COMPANIES, SITE_PRIORITY
from saramin_web import fetch_saramin
from jobkorea_web import fetch_jobkorea
from jobplanet_web import fetch_jobplanet
from jobkorea_company import fetch_companies  # 잡코리아(매출) + 사람인(사원수) 결합

TODAY = datetime.date.today().isoformat()
REFRESH_DAYS = int(os.environ.get("COMPANY_REFRESH_DAYS", "30"))


def read_csv(path, columns):
    if not path.exists():
        return {}
    out = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            rid = row.get("id")
            if rid:
                out[rid] = {c: row.get(c, "") for c in columns}
    return out


def write_csv(path, columns, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in columns})


def _norm(s):
    """회사명/직무명 정규화 — 사이트 간 중복 판정용.
    법인격 표기((주)·㈜·주식회사 등)를 먼저 제거한 뒤 기호/공백을 제거한다."""
    n = re.sub(r"㈜|\((?:주|유|사|재|합|학|의)\)|주식회사", "", s or "")
    n = re.sub(r"[\s\(\)（）\[\]【】·,./'\"-]", "", n)
    return n.lower()


def collect_multisite():
    """모든 사이트의 공고를 수집해 합친다.
    (회사+직무+분류) 완전일치 중복은 status/마감일을 아는 merge 이후 dedup_jobs에서 처리한다."""
    fetchers = {
        "사람인": fetch_saramin,
        "잡코리아": fetch_jobkorea,
        "잡플래닛": fetch_jobplanet,
    }
    out = []
    for site in SITE_PRIORITY:
        fn = fetchers.get(site)
        if not fn:
            continue
        rows = fn() or []
        out.extend(rows)
        print(f"[multisite] {site}: {len(rows)}건 수집")
    return out


def _deadline_rank(deadline):
    """마감 임박도(작을수록 임박). 'MM/DD'는 남은 일수, 상시/미정/형식불명은 큰 값."""
    s = (deadline or "").strip()
    m = re.match(r"(\d{1,2})/(\d{1,2})", s)
    if not m:
        return 10 ** 6  # 상시·미정 → 맨 뒤
    mo, da = int(m.group(1)), int(m.group(2))
    today = datetime.date.today()
    try:
        due = datetime.date(today.year, mo, da)
    except ValueError:
        return 10 ** 6
    if due < today - datetime.timedelta(days=1):
        due = datetime.date(today.year + 1, mo, da)  # 연말→연초 보정
    return (due - today).days


def dedup_jobs(jobs):
    """(회사+직무+분류) 완전일치 중복을 1건으로 축약.
    선택 규칙: ① 모집중을 마감보다 우선(=마감 지났어도 살아있는 동일공고 노출),
              ② 그 안에서 마감 임박(가까운 마감일) 우선."""
    groups = {}
    for j in jobs:
        key = (_norm(j.get("company")), _norm(j.get("role")), j.get("category", ""))
        groups.setdefault(key, []).append(j)

    def pick_key(j):
        alive = 0 if j.get("status") == "모집중" else 1
        return (alive, _deadline_rank(j.get("deadline")))

    out, dropped = [], 0
    for grp in groups.values():
        if len(grp) > 1:
            grp.sort(key=pick_key)
            dropped += len(grp) - 1
        out.append(grp[0])
    print(f"[dedup] (회사+직무+분류) 완전일치 중복 {dropped}건 제거 → {len(out)}건")
    return out


def merge_jobs(scraped):
    """기존 jobs.csv + 새 스냅샷을 id 기준 병합."""
    existing = read_csv(OUT_JOBS, JOB_COLUMNS)

    # 새 스냅샷에서 id 중복 제거 (먼저 잡힌 분류 우선 = CATEGORY_QUERIES 순서)
    fresh = {}
    for j in scraped:
        jid = j.get("id")
        if jid and jid not in fresh:
            fresh[jid] = j
    fresh_ids = set(fresh)

    merged = {}
    # 1) 기존 공고: 이번에 안 잡혔으면 마감 처리, 잡혔으면 아래서 갱신
    for jid, old in existing.items():
        if jid not in fresh_ids:
            old["status"] = "마감"
            merged[jid] = old
    # 2) 이번에 잡힌 공고: 정보 갱신, 모집중
    for jid, j in fresh.items():
        row = dict(j)
        row["status"] = "모집중"
        row["last_seen"] = TODAY
        merged[jid] = row

    n_new = len(fresh_ids - set(existing))
    n_closed = sum(1 for r in merged.values() if r["status"] == "마감")
    print(f"[jobs] 신규 {n_new} · 모집중 {len(fresh_ids)} · 마감 {n_closed} · 총 {len(merged)}")
    return list(merged.values())


def manage_companies(jobs):
    """현재 공고에 등장한 회사(csn)를 companies.csv로 누적. 신규/오래된 것만 조회."""
    existing = read_csv(OUT_COMPANIES, COMPANY_COLUMNS)
    # 현재 공고의 회사 목록 {csn: name}
    targets = {}
    for j in jobs:
        cid = j.get("company_id")
        if cid:
            targets.setdefault(cid, j.get("company", ""))

    def stale(cid):
        d = existing.get(cid, {}).get("last_updated", "")
        if not d:
            return True
        try:
            age = (datetime.date.fromisoformat(TODAY) - datetime.date.fromisoformat(d)).days
            return age >= REFRESH_DAYS
        except ValueError:
            return True

    to_fetch = {cid: name for cid, name in targets.items() if cid not in existing or stale(cid)}
    print(f"[company] 대상 {len(targets)}개 중 {len(to_fetch)}개 신규/갱신 조회")

    if to_fetch:
        for info in fetch_companies(to_fetch):
            info["last_updated"] = TODAY
            existing[info["id"]] = info

    # 현재 공고에 등장하는 회사만 유지(고아 정리)
    return [existing[cid] for cid in targets if cid in existing]


def main():
    scraped = collect_multisite()
    jobs = merge_jobs(scraped)
    jobs = dedup_jobs(jobs)
    write_csv(OUT_JOBS, JOB_COLUMNS, jobs)

    companies = manage_companies(jobs)
    write_csv(OUT_COMPANIES, COMPANY_COLUMNS, companies)

    print(f"\n✅ jobs {len(jobs)}건 → {OUT_JOBS}")
    print(f"✅ companies {len(companies)}개 → {OUT_COMPANIES}")


if __name__ == "__main__":
    main()
