"""사람인 웹 검색 스크래퍼 (requests + BeautifulSoup) — 분류별 검색 방식.

각 분류(category)에 정의된 검색어들로 사람인을 검색하고, 결과를 그 분류로 태깅한다.
사후 키워드 추정이 아니라 '검색 의도' 기반이라 분류 정확도가 높다.

공식 Open API 키 없이 동작 (검색결과가 서버 렌더링). 약관/robots 준수, 딜레이 유지.
"""
import time
import urllib.parse
import requests
from bs4 import BeautifulSoup

from config import CATEGORY_QUERIES

BASE = "https://www.saramin.co.kr"
SEARCH = BASE + "/zf_user/search/recruit"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
}


def _txt(node):
    return node.get_text(strip=True) if node else ""


def _search_one(session, query, category, max_pages):
    """검색어 1개로 여러 페이지를 긁어 rows 리스트 반환."""
    rows = []
    for page in range(1, max_pages + 1):
        params = {"searchword": query, "exp_cd": "1",
                  "recruitPage": page, "recruitPageCount": 40}
        r = None
        for attempt in range(3):  # 간헐적 DNS/타임아웃 재시도
            try:
                r = session.get(SEARCH, params=params, timeout=20)
                r.raise_for_status()
                break
            except Exception as e:
                print(f"    [{category}] '{query}' p{page} 재시도 {attempt+1}/3: {e}")
                time.sleep(2)
        if r is None:
            break
        soup = BeautifulSoup(r.text, "html.parser")
        items = soup.select(".item_recruit")
        if not items:
            break
        for it in items:
            idx = it.get("value")
            a = it.select_one("h2.job_tit a")
            if not idx or not a:
                continue
            title = a.get("title", "").strip()
            href = a.get("href", "")
            url = urllib.parse.urljoin(BASE, href.split("&searchword")[0]) if href else ""
            conds = [_txt(x) for x in it.select(".job_condition span")]
            sector = ", ".join(_txt(x) for x in it.select(".job_sector a")[:4])
            rows.append({
                "_idx": idx,
                "company": _txt(it.select_one(".area_corp .corp_name a")),
                "role": title,
                "category": category,
                "description": sector,
                "requirements": " / ".join(filter(None, conds[1:4])),
                "location": conds[0] if conds else "",
                "deadline": _txt(it.select_one(".job_date .date")).replace("~", "").strip(),
                "salary": "",
                "revenue": "",
                "source": "사람인",
                "url": url,
            })
        time.sleep(0.5)  # 매너 딜레이
    return rows


def fetch_saramin(max_pages=2):
    """CATEGORY_QUERIES 순서대로 분류별 검색. 정의 순서가 곧 우선순위."""
    s = requests.Session()
    s.headers.update(HEADERS)
    all_rows = []
    for category, queries in CATEGORY_QUERIES.items():
        cnt = 0
        for query in queries:
            got = _search_one(s, query, category, max_pages)
            all_rows.extend(got)
            cnt += len(got)
        print(f"[saramin] {category}: {cnt}건(중복 전)")
    print(f"[saramin] 총 {len(all_rows)}건(중복 전) 수집")
    return all_rows


if __name__ == "__main__":
    rows = fetch_saramin(max_pages=1)
    for r in rows[:8]:
        print(r["category"], "|", r["company"], "|", r["role"][:30])
