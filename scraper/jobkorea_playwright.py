"""잡코리아 스크래퍼 (Playwright).

잡코리아는 공식 API가 없고 anti-bot이 강해 일반 requests로는 403이 잦다.
헤드리스 브라우저로 검색결과 페이지를 렌더링해 공고 카드를 파싱한다.

사용 전:
  pip install playwright
  playwright install chromium

주의: 사이트 구조가 바뀌면 선택자(selector) 업데이트가 필요하다.
      과도한 요청은 차단/법적 이슈가 될 수 있으니 딜레이를 유지할 것.
"""
import urllib.parse

from config import COMMON_KEYWORDS, classify_str

SEARCH = "https://www.jobkorea.co.kr/Search/?stext={kw}&careerType=1"  # careerType=1 신입


def fetch_jobkorea(max_pages: int = 2):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[jobkorea] playwright 미설치 → 건너뜀 (pip install playwright && playwright install chromium)")
        return []

    rows, seen = [], set()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0 Safari/537.36"),
            locale="ko-KR",
        )
        page = ctx.new_page()
        for kw in COMMON_KEYWORDS:
            url = SEARCH.format(kw=urllib.parse.quote(kw))
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_selector("article.list-item, .list-default .post", timeout=8000)
            except Exception as e:
                print(f"[jobkorea] '{kw}' 로드 실패: {e}")
                continue

            # 공고 카드 파싱 (선택자는 사이트 변경 시 조정 필요)
            cards = page.query_selector_all("article.list-item, .list-default .post")
            for c in cards:
                try:
                    a = c.query_selector("a.information-title-link, .title a")
                    if not a:
                        continue
                    title = (a.inner_text() or "").strip()
                    href = a.get_attribute("href") or ""
                    if href.startswith("/"):
                        href = "https://www.jobkorea.co.kr" + href
                    if href in seen or not title:
                        continue
                    seen.add(href)
                    comp_el = c.query_selector(".company-name, .name")
                    loc_el = c.query_selector(".chip-information-group .chip:nth-child(2), .option .loc")
                    comp = (comp_el.inner_text().strip() if comp_el else "")
                    rows.append({
                        "id": href,          # 잡코리아는 rec_idx 없음 → url을 id로
                        "company_id": "",
                        "role": title,
                        "category": classify_str(title),
                        "company": comp,
                        "description": "",
                        "requirements": "신입",
                        "location": (loc_el.inner_text().strip() if loc_el else ""),
                        "deadline": "",
                        "salary": "",
                        "source": "잡코리아",
                        "url": href,
                    })
                except Exception:
                    continue
            page.wait_for_timeout(800)  # 매너 딜레이
        browser.close()

    print(f"[jobkorea] {len(rows)}건 수집")
    return rows


if __name__ == "__main__":
    for row in fetch_jobkorea()[:5]:
        print(row)
