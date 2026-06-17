"""잡플래닛 스크래퍼 (Playwright).

잡플래닛 채용 검색은 JS 렌더링 + 상당수 기능이 로그인 게이트다.
공개 채용 목록 페이지를 헤드리스로 렌더링해 파싱을 시도하되,
로그인이 필요하면 환경변수로 받은 계정으로 로그인한다.

사용 전:
  pip install playwright && playwright install chromium
  (선택) export JOBPLANET_ID=... JOBPLANET_PW=...

주의: 약관상 로그인 스크래핑은 제약이 있을 수 있다. 개인 용도/저빈도로만.
      선택자는 사이트 변경 시 조정 필요. 미설치/실패 시 빈 리스트 반환.
"""
import os
import urllib.parse

from config import COMMON_KEYWORDS, classify_str

SEARCH = "https://www.jobplanet.co.kr/job/search?q={kw}"


def fetch_jobplanet(max_keywords=None):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[잡플래닛] playwright 미설치 → 건너뜀")
        return []

    jp_id, jp_pw = os.environ.get("JOBPLANET_ID"), os.environ.get("JOBPLANET_PW")
    rows, seen = [], set()
    kws = COMMON_KEYWORDS[:max_keywords] if max_keywords else COMMON_KEYWORDS

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(locale="ko-KR")
            page = ctx.new_page()

            if jp_id and jp_pw:
                try:
                    page.goto("https://www.jobplanet.co.kr/users/sign_in", timeout=20000)
                    page.fill("input[name='user[email]']", jp_id)
                    page.fill("input[name='user[password]']", jp_pw)
                    page.click("button[type='submit']")
                    page.wait_for_timeout(2000)
                except Exception as e:
                    print(f"[잡플래닛] 로그인 실패(계속 진행): {e}")

            for kw in kws:
                url = SEARCH.format(kw=urllib.parse.quote(kw))
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_selector("a[href*='/job/']", timeout=8000)
                except Exception as e:
                    print(f"[잡플래닛] '{kw}' 로드 실패: {e}")
                    continue
                cards = page.query_selector_all("[class*='JobCard'], li[class*='result']")
                for c in cards:
                    try:
                        a = c.query_selector("a[href*='/job/']")
                        if not a:
                            continue
                        href = a.get_attribute("href") or ""
                        if href.startswith("/"):
                            href = "https://www.jobplanet.co.kr" + href
                        title = (a.inner_text() or "").strip().split("\n")[0]
                        if not title or href in seen:
                            continue
                        seen.add(href)
                        comp_el = c.query_selector("[class*='company'], [class*='Company']")
                        rows.append({
                            "id": href,
                            "company_id": "",
                            "role": title,
                            "category": classify_str(title),
                            "company": (comp_el.inner_text().strip() if comp_el else ""),
                            "description": "",
                            "requirements": "",
                            "location": "",
                            "deadline": "",
                            "salary": "",
                            "source": "잡플래닛",
                            "url": href,
                        })
                    except Exception:
                        continue
                page.wait_for_timeout(800)
            browser.close()
    except Exception as e:
        print(f"[잡플래닛] 오류 → 건너뜀: {e}")
        return rows

    print(f"[잡플래닛] {len(rows)}건 수집")
    return rows


if __name__ == "__main__":
    for r in fetch_jobplanet(max_keywords=2)[:5]:
        print(r)
