"""회사 매출액 보강 (DART OpenAPI).

채용 API에는 매출액이 없으므로 회사명 -> 고유번호(corp_code) -> 최근 매출액 순으로 조회.
사용 전:
  1) https://opendart.fss.or.kr 에서 무료 API 키 발급
  2) export DART_API_KEY=발급받은키

간단 구현: corpCode.xml(전체 기업 목록)을 받아 회사명 매칭 후 단일회사 주요계정 조회.
미설정 시 매출액은 빈칸으로 둔다 (HTML에서 '확인필요' 표시).
"""
import os
import io
import re
import zipfile
import threading
import xml.etree.ElementTree as ET
import requests

CORP_CODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"
FIN_URL = "https://opendart.fss.or.kr/api/fnlttSinglAcnt.json"

_corp_index = None  # 정규화된 회사명 -> [corp_code, ...]
_index_lock = threading.Lock()  # 병렬 시 corpCode.xml 1회만 로드


def _norm(name: str) -> str:
    """동일성 비교용: 주식회사/(주)/㈜/괄호/공백 제거 + 소문자."""
    n = re.sub(r"주식회사|㈜|\((?:주|유|사|재|합|학|의)\)|\(.*?\)", "", name or "")
    return re.sub(r"\s+", "", n).lower()


def _load_corp_index(key):
    global _corp_index
    if _corp_index is not None:
        return _corp_index
    with _index_lock:
        if _corp_index is not None:   # 락 대기 중 다른 스레드가 로드했을 수 있음
            return _corp_index
        return _build_corp_index(key)


def _build_corp_index(key):
    global _corp_index
    r = requests.get(CORP_CODE_URL, params={"crtfc_key": key}, timeout=30)
    z = zipfile.ZipFile(io.BytesIO(r.content))
    root = ET.fromstring(z.read(z.namelist()[0]))
    _corp_index = {}
    for el in root.iter("list"):
        name = (el.findtext("corp_name") or "").strip()
        code = (el.findtext("corp_code") or "").strip()
        if name and code:
            _corp_index.setdefault(_norm(name), []).append(code)
    return _corp_index


def _fmt(won: int, year: str) -> str:
    eok = won / 1e8
    if eok >= 10000:
        return f"{eok/10000:,.1f}조원({year})"
    return f"{eok:,.0f}억원({year})"


def _api_key():
    """DART 키: 환경변수 우선, 없으면 scraper/.dart_key 파일(gitignore됨)."""
    key = os.environ.get("DART_API_KEY")
    if key:
        return key.strip()
    try:
        p = os.path.join(os.path.dirname(__file__), ".dart_key")
        with open(p, encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def revenue_for(company: str, years=("2024", "2023", "2022")) -> str:
    """DART에서 매출액 조회. 회사명 100% 일치(정규화) + 단일 매칭일 때만 반환.
    동명 회사가 둘 이상이면(모호) 빈 문자열."""
    key = _api_key()
    if not key or not company:
        return ""
    try:
        idx = _load_corp_index(key)
        codes = idx.get(_norm(company), [])
        if len(codes) != 1:        # 미존재 or 동명 모호 → 안전하게 미상
            return ""
        code = codes[0]
        for year in years:
            r = requests.get(FIN_URL, params={
                "crtfc_key": key, "corp_code": code,
                "bsns_year": year, "reprt_code": "11011",  # 사업보고서
            }, timeout=15).json()
            if r.get("status") != "000":
                continue
            for item in r.get("list", []):
                if item.get("account_nm") == "매출액" and item.get("fs_div") in (None, "CFS", "OFS"):
                    amt = (item.get("thstrm_amount") or "").replace(",", "")
                    if amt.lstrip("-").isdigit():
                        return _fmt(int(amt), year)
    except Exception:
        return ""
    return ""
