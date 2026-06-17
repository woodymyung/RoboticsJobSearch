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
import zipfile
import xml.etree.ElementTree as ET
import requests

CORP_CODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"
FIN_URL = "https://opendart.fss.or.kr/api/fnlttSinglAcnt.json"

_corp_map = None


def _load_corp_map(key):
    global _corp_map
    if _corp_map is not None:
        return _corp_map
    r = requests.get(CORP_CODE_URL, params={"crtfc_key": key}, timeout=30)
    z = zipfile.ZipFile(io.BytesIO(r.content))
    root = ET.fromstring(z.read(z.namelist()[0]))
    _corp_map = {}
    for el in root.iter("list"):
        name = (el.findtext("corp_name") or "").strip()
        code = (el.findtext("corp_code") or "").strip()
        if name:
            _corp_map[name] = code
    return _corp_map


def revenue_for(company: str, year: str = "2024") -> str:
    key = os.environ.get("DART_API_KEY")
    if not key or not company:
        return ""
    try:
        corp_map = _load_corp_map(key)
        code = corp_map.get(company)
        if not code:  # 부분 일치 시도
            for n, c in corp_map.items():
                if company in n or n in company:
                    code = c
                    break
        if not code:
            return ""
        r = requests.get(FIN_URL, params={
            "crtfc_key": key, "corp_code": code,
            "bsns_year": year, "reprt_code": "11011",  # 사업보고서
        }, timeout=15).json()
        for item in r.get("list", []):
            if item.get("account_nm") == "매출액":
                amt = item.get("thstrm_amount", "").replace(",", "")
                if amt.isdigit():
                    return f"{int(amt)/1e8:,.0f}억원({year})"
    except Exception:
        return ""
    return ""
