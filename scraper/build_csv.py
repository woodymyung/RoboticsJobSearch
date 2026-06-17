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
from jobkorea_playwright import fetch_jobkorea
from jobplanet_playwright import fetch_jobplanet
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
    """회사명/직무명 정규화 — 사이트 간 중복 판정용."""
    s = (s or "").lower()
    s = re.sub(r"[\s\(\)（）㈜\[\]【】·,./'\"-]", "", s)
    s = s.replace("주식회사", "").replace("(주)", "")
    return s


def collect_multisite():
    """SITE_PRIORITY 순서로 사이트별 수집 후, (회사+직무) 기준 교차 중복 제거.
    우선순위 높은 사이트의 공고를 유지한다."""
    fetchers = {
        "사람인": fetch_saramin,
        "잡코리아": fetch_jobkorea,
        "잡플래닛": fetch_jobplanet,
    }
    out, seen = [], set()
    for site in SITE_PRIORITY:
        fn = fetchers.get(site)
        if not fn:
            continue
        rows = fn() or []
        kept = 0
        for r in rows:
            key = (_norm(r.get("company")), _norm(r.get("role")))
            if key in seen:
                continue  # 이미 더 높은 우선순위 사이트에 있음
            seen.add(key)
            out.append(r)
            kept += 1
        print(f"[multisite] {site}: {len(rows)}건 중 {kept}건 채택(교차 중복 제외)")
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
    write_csv(OUT_JOBS, JOB_COLUMNS, jobs)

    companies = manage_companies(jobs)
    write_csv(OUT_COMPANIES, COMPANY_COLUMNS, companies)

    print(f"\n✅ jobs {len(jobs)}건 → {OUT_JOBS}")
    print(f"✅ companies {len(companies)}개 → {OUT_COMPANIES}")


if __name__ == "__main__":
    main()
