"""잡코리아 기업정보 스크래퍼 (회사명 → 매출액·사원수 등).

사람인 회사페이지는 매출액이 JS로 로딩돼 정적 HTML에 없다.
반면 잡코리아 기업정보 페이지는 매출액·사원수·설립일·산업을 정적 HTML로 노출한다.
회사명으로 잡코리아 기업검색 → 회사 페이지 파싱. requests+bs4, API 키 불필요.

병렬(ThreadPoolExecutor)로 처리해 수백 개도 1~2분 내 수집한다.
"""
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.parse
import requests
from bs4 import BeautifulSoup

from config import COMPANY_COLUMNS
from saramin_company import _parse_company, VIEW as SR_VIEW
from enrich_revenue import revenue_for  # DART 매출(키 있을 때만)

CORP_SEARCH = "https://www.jobkorea.co.kr/Search/?tabType=corp&stext={kw}"
COMPANY = "https://www.jobkorea.co.kr/company/{cid}"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
}
MAX_WORKERS = 12

_local = threading.local()


def _session():
    if not hasattr(_local, "s"):
        _local.s = requests.Session()
        _local.s.headers.update(HEADERS)
    return _local.s


def _get(url, params=None, tries=3):
    s = _session()
    for attempt in range(tries):
        try:
            r = s.get(url, params=params, timeout=20)
            if r.status_code == 200:
                return r.text
            return ""
        except Exception:
            if attempt < tries - 1:
                time.sleep(1.5)
    return ""


def _clean(name):
    """검색 매칭용 회사명 정리: (주)/㈜/괄호 제거."""
    n = re.sub(r"㈜|\((?:주|유|사|재|합|학|의)\)|\(.*?\)", "", name or "")
    return n.strip()


def _norm(name):
    """이름 동일성 비교용: (주)/㈜/괄호/공백 제거 + 소문자."""
    return re.sub(r"\s+", "", _clean(name)).lower()


def _find_company_id(name):
    """잡코리아 기업검색 결과 중 회사명이 100% 일치하는 회사 id만 반환.
    (동명/유사 회사 오매칭 방지 — 예: '로직스' 검색 시 '삼성바이오로직스' 채택 금지)"""
    html = _get(CORP_SEARCH.format(kw=urllib.parse.quote(_clean(name))))
    if not html:
        return ""
    target = _norm(name)
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=re.compile(r"/company/\d+", re.I)):
        if _norm(a.get_text(strip=True)) == target:
            m = re.search(r"/company/(\d+)", a["href"], re.I)
            if m:
                return m.group(1)
    return ""  # 정확히 일치하는 회사명 없음 → 매출액 미상


def _parse(html):
    """잡코리아 회사페이지에서 라벨→값 추출."""
    soup = BeautifulSoup(html, "html.parser")
    found = {}
    labels = {"매출액": "revenue", "사원수": "employees", "설립일": "founded",
              "산업": "industry", "기업형태": "biz_type", "기업규모": "biz_type",
              "홈페이지": "homepage"}
    for tag in soup.find_all(["dt", "th", "strong", "span", "li"]):
        txt = tag.get_text(strip=True)
        for lab, key in labels.items():
            if key in found:
                continue
            if txt.startswith(lab) and len(txt) <= len(lab) + 2:
                sib = tag.find_next(["dd", "td", "span", "strong", "b", "a"])
                val = sib.get_text(strip=True) if sib else ""
                if val:
                    found[key] = val[:40]
    return found


def _fetch_one(csn, name):
    info = {c: "" for c in COMPANY_COLUMNS}
    info["id"] = csn
    info["name"] = name

    # 1) 잡코리아 — 매출액 우선(큰 회사 위주로 노출)
    cid = _find_company_id(name)
    if cid:
        info["url"] = COMPANY.format(cid=cid)
        jk = _parse(_get(COMPANY.format(cid=cid)))
        for k, v in jk.items():
            if v:
                info[k] = v

    # 2) 사람인 fallback(csn 직접) — 빈 칸 보강(특히 SME 사원수/규모/업종)
    if csn and (not info["employees"] or not info["industry"]):
        sr_html = _get(SR_VIEW, params={"csn": csn})
        if sr_html:
            for k, v in _parse_company(sr_html).items():
                if v and not info.get(k):
                    info[k] = v
            if not info["url"]:
                info["url"] = f"{SR_VIEW}?csn={csn}"

    # 3) 매출액은 DART 우선(공식·정확). 키 없으면 즉시 "" 반환되어 잡코리아 값 유지.
    dart_rev = revenue_for(name)
    if dart_rev:
        info["revenue"] = dart_rev
    return info


def fetch_companies(targets):
    """targets: {csn: name}. 잡코리아에서 회사정보 병렬 수집."""
    out, total, done = [], len(targets), 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_fetch_one, csn, name): csn for csn, name in targets.items()}
        for f in as_completed(futs):
            try:
                out.append(f.result())
            except Exception:
                pass
            done += 1
            if done % 50 == 0:
                print(f"  [company] {done}/{total} 진행")
    got = sum(1 for c in out if c["revenue"] or c["employees"])
    print(f"[company] {len(out)}개 중 {got}개 규모정보 수집 (매출/사원수)")
    return out


if __name__ == "__main__":
    import csv
    rows = list(csv.DictReader(open("../jobs.csv", encoding="utf-8-sig")))
    t = {}
    for r in rows:
        if r["company_id"] and r["company_id"] not in t:
            t[r["company_id"]] = r["company"]
        if len(t) >= 10:
            break
    t0 = time.time()
    for c in fetch_companies(t):
        print(f"  {c['name'][:16]:16} | 매출:{c['revenue'] or '-':14} | 사원:{c['employees'] or '-':8} | {c['industry'][:12] or '-'}")
    print(f"10개 {time.time()-t0:.1f}초")
