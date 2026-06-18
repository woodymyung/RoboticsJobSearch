"""잡코리아 공고 → 사람인 회사 고유번호(csn) 해석.

잡코리아 공고엔 사람인 csn이 없어 companies.csv(=csn 키) 및 DART/규모 보강과
연결되지 않는다. 회사명으로 사람인 기업검색을 돌려 '정확히 일치'하는 회사의
csn만 채택한다(동명이인·부분일치로 인한 오매칭 방지).

csn을 얻으면 build_csv의 manage_companies가 그 회사를 DART(매출)+잡코리아/사람인
프로필(사원수·규모·업종)로 자동 보강한다.
"""
import re
import time
import urllib.parse
import requests
from bs4 import BeautifulSoup

SEARCH = "https://www.saramin.co.kr/zf_user/search/company"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
}


def _norm(name):
    """동일성 비교용 정규화: 법인격 표기·괄호·기호·공백 제거 + 소문자."""
    n = re.sub(r"㈜|\((?:주|유|사|재|합|학|의)\)|\(.*?\)", "", name or "")
    n = re.sub(r"[\s\(\)（）\[\]【】·,./'\"-]", "", n)
    return n.replace("주식회사", "").lower()


def _resolve_one(session, name):
    """회사명으로 사람인 기업검색 → 정규화 후 정확히 일치하는 회사의 csn 반환('' 없음)."""
    target = _norm(name)
    if not target:
        return ""
    try:
        r = session.get(SEARCH, params={"searchType": "search", "searchword": name}, timeout=20)
        r.raise_for_status()
    except Exception:
        return ""
    soup = BeautifulSoup(r.text, "html.parser")
    for a in soup.select("a[href*='company-info/view?csn=']"):
        cname = a.get_text(strip=True)
        if cname and _norm(cname) == target:
            m = re.search(r"csn=([^&\"']+)", a["href"])
            if m:
                return m.group(1)
    return ""


def resolve_csns(names, delay=0.4):
    """고유 회사명 집합 → {name: csn}. 매칭된 것만 담는다."""
    s = requests.Session()
    s.headers.update(HEADERS)
    out, hit = {}, 0
    names = [n for n in dict.fromkeys(names) if n]  # 중복 제거·순서 유지
    for i, name in enumerate(names, 1):
        csn = _resolve_one(s, name)
        if csn:
            out[name] = csn
            hit += 1
        if i % 50 == 0:
            print(f"  [csn] {i}/{len(names)} 진행 (매칭 {hit})")
        time.sleep(delay)  # 매너 딜레이
    print(f"[csn] {len(names)}개 중 {hit}개 csn 매칭")
    return out


if __name__ == "__main__":
    print(resolve_csns(["위로보틱스", "에이치엘로보틱스", "하이크로봇코리아"]))
