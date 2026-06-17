"""사람인 기업정보 스크래퍼 (csn 기반) + DART 매출액 보강.

회사 고유번호(csn)로 기업정보 페이지에서 사원수·설립·업종·홈페이지를 파싱한다.
매출액은 사람인 정적 HTML엔 없으므로(JS 차트) DART OpenAPI로 보강한다.
"""
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup

from config import COMPANY_COLUMNS
from enrich_revenue import revenue_for

MAX_WORKERS = 12          # 병렬 요청 수
_local = threading.local()  # 스레드별 requests.Session


def _session():
    if not hasattr(_local, "s"):
        _local.s = requests.Session()
        _local.s.headers.update(HEADERS)
    return _local.s

BASE = "https://www.saramin.co.kr"
VIEW = BASE + "/zf_user/company-info/view"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
}


def _parse_company(html):
    soup = BeautifulSoup(html, "html.parser")
    summary = soup.select_one(".company_summary")
    details = soup.select_one(".company_details")
    s_txt = summary.get_text(" ", strip=True) if summary else ""
    d_txt = details.get_text(" | ", strip=True) if details else ""

    def after(label, text):
        m = re.search(re.escape(label) + r"\s*\|\s*([^|]+)", text)
        return m.group(1).strip() if m else ""

    founded = ""
    m = re.search(r"(\d{4}년\s*\d{1,2}월\s*\d{1,2}일)\s*설립", s_txt)
    if m:
        founded = m.group(1)
    emp = ""
    m = re.search(r"([0-9,]+)\s*명", s_txt)
    if m:
        emp = m.group(1) + "명"
    biz = ""
    m = re.search(r"기업형태\s*[:：]?\s*([^,|]+)", s_txt)
    if m:
        biz = m.group(1).strip()
    return {
        "founded": founded,
        "employees": emp,
        "biz_type": biz,
        "industry": after("업종", d_txt),
        "homepage": after("홈페이지", d_txt),
    }


def fetch_companies(targets, session=None, sleep=0.5):
    """targets: {csn: name} 딕셔너리. 회사 정보 리스트 반환."""
    s = session or requests.Session()
    s.headers.update(HEADERS)
    out = []
    total = len(targets)
    for i, (csn, name) in enumerate(targets.items(), 1):
        info = {c: "" for c in COMPANY_COLUMNS}
        info["id"] = csn
        info["name"] = name
        info["url"] = f"{VIEW}?csn={csn}"
        for attempt in range(3):
            try:
                r = s.get(VIEW, params={"csn": csn}, timeout=20)
                if r.status_code == 200:
                    info.update(_parse_company(r.text))
                break
            except Exception as e:
                if attempt == 2:
                    print(f"  [company] {name} 오류: {e}")
                else:
                    time.sleep(2)
        info["revenue"] = revenue_for(name) or ""  # DART (키 없으면 빈칸)
        out.append(info)
        if i % 20 == 0:
            print(f"  [company] {i}/{total} 진행")
        time.sleep(sleep)
    print(f"[company] {len(out)}개 회사 정보 수집")
    return out
