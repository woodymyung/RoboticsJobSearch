"""STEP 2 — 잡코리아 공고의 회사 연결 + 보강 (사람인 csn 조회 없이).

① companies.csv에 회사명이 정확히 일치(정규화 후)하면 → 그 회사 id로 연결(재조회 X).
② 없으면 → 회사명으로 잡코리아 기업프로필(규모) + DART(매출) 직접 조회 후 신규 추가.
   잡코리아 전용 회사엔 합성 id 'jk:<정규화명>'을 부여한다.

DART 키는 .env(DART_API_KEY) 또는 환경변수에서 읽는다.
"""
import csv
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import OUT_JOBS, OUT_COMPANIES, JOB_COLUMNS, COMPANY_COLUMNS
import datetime
from jobkorea_company import _find_company_id, _parse, _get, COMPANY
from enrich_revenue import revenue_for

TODAY = datetime.date.today().isoformat()


def _load_env():
    p = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(p) and not os.environ.get("DART_API_KEY"):
        for line in open(p):
            if line.startswith("DART_API_KEY="):
                os.environ["DART_API_KEY"] = line.split("=", 1)[1].strip()


def _norm(name):
    n = re.sub(r"㈜|\((?:주|유|사|재|합|학|의)\)|\(.*?\)", "", name or "")
    n = re.sub(r"[\s\(\)（）\[\]【】·,./'\"-]", "", n)
    return n.replace("주식회사", "").lower()


def _read(path, cols):
    return list(csv.DictReader(open(path, encoding="utf-8-sig")))


def _write(path, cols, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _enrich_new(name):
    """잡코리아 프로필(규모) + DART(매출)로 신규 회사 정보 구성."""
    info = {c: "" for c in COMPANY_COLUMNS}
    info["id"] = "jk:" + _norm(name)
    info["name"] = name
    cid = _find_company_id(name)          # 잡코리아 기업 id
    if cid:
        info["url"] = COMPANY.format(cid=cid)
        for k, v in _parse(_get(COMPANY.format(cid=cid))).items():
            if v:
                info[k] = v
    dart = revenue_for(name)               # DART 매출(공식·정확, 없으면 "")
    if dart:
        info["revenue"] = dart
    info["last_updated"] = TODAY
    return info


def main():
    _load_env()
    print("DART_API_KEY:", "설정됨" if os.environ.get("DART_API_KEY") else "없음(매출 잡코리아값만)")

    jobs = _read(OUT_JOBS, JOB_COLUMNS)
    comps = _read(OUT_COMPANIES, COMPANY_COLUMNS)
    name2id = {_norm(c["name"]): c["id"] for c in comps if c.get("name")}

    jk = [r for r in jobs if not r.get("company_id") and r.get("company")]
    matched, todo = 0, {}   # todo: {norm: 원본명}
    for r in jk:
        nm = _norm(r["company"])
        if not nm:
            continue
        if nm in name2id:                  # ① 기존 회사와 정확 일치 → 연결
            r["company_id"] = name2id[nm]
            matched += 1
        else:                              # ② 신규 → DART 조회 대상
            todo.setdefault(nm, r["company"])
    print(f"[link] company_id 미보유 공고 {len(jk)}건 · 기존 회사 연결 {matched}건 · 신규 회사 {len(todo)}개 DART 조회")

    # ② 신규 회사 병렬 보강
    new_rows = []
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(_enrich_new, name): nm for nm, name in todo.items()}
        done = 0
        for f in as_completed(futs):
            nm = futs[f]
            try:
                info = f.result()
                name2id[nm] = info["id"]
                new_rows.append(info)
            except Exception as e:
                print(f"  [warn] {todo[nm]} 실패: {e}")
            done += 1
            if done % 50 == 0:
                print(f"  [dart] {done}/{len(todo)} 진행")

    # 신규 회사의 company_id를 공고에 반영
    for r in jk:
        if not r.get("company_id"):
            r["company_id"] = name2id.get(_norm(r["company"]), "")

    got = sum(1 for c in new_rows if c["revenue"] or c["employees"])
    print(f"[dart] 신규 {len(new_rows)}개 중 {got}개 매출/규모 확보")

    _write(OUT_JOBS, JOB_COLUMNS, jobs)
    _write(OUT_COMPANIES, COMPANY_COLUMNS, comps + new_rows)
    print(f"✅ jobs.csv 갱신(잡코리아 company_id 연결) · companies.csv +{len(new_rows)}개")


if __name__ == "__main__":
    main()
