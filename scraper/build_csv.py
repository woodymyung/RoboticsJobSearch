"""오케스트레이터: 모든 소스 수집 -> 중복 제거 -> 매출액 보강 -> jobs.csv 저장.

실행:
  cd scraper
  pip install -r requirements.txt
  python build_csv.py

환경변수(선택):
  SARAMIN_ACCESS_KEY  사람인 Open API 키
  DART_API_KEY        매출액 보강용 DART 키
"""
import csv

from config import COLUMNS, OUT_CSV
from saramin_web import fetch_saramin   # requests+bs4 (API 키 불필요, 실동작)
from jobkorea_playwright import fetch_jobkorea
from enrich_revenue import revenue_for


def dedupe(rows):
    """rec_idx 기준 중복 제거. 먼저 등장한 것을 유지 → CATEGORY_QUERIES 순서가 우선순위."""
    seen, out = set(), []
    for r in rows:
        key = r.get("_idx") or (r.get("company", ""), r.get("role", ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def main():
    rows = []
    rows += fetch_saramin()
    rows += fetch_jobkorea()
    rows = dedupe(rows)

    # 매출액 보강 (회사별 1회만 조회 후 캐시)
    cache = {}
    for r in rows:
        comp = r.get("company", "")
        if comp and not r.get("revenue"):
            if comp not in cache:
                cache[comp] = revenue_for(comp)
            r["revenue"] = cache[comp]

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLUMNS})

    print(f"\n✅ 총 {len(rows)}건 -> {OUT_CSV}")


if __name__ == "__main__":
    main()
