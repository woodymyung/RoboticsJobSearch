"""잡플래닛 검색 스크래퍼 (curl_cffi + 내부 JSON API).

잡플래닛은 Cloudflare WAF로 일반 requests는 403이다. curl_cffi(chrome TLS 모사)로
우회하고, 페이지가 내부적으로 호출하는 검색 API를 직접 사용한다:
    GET /api/v3/job/postings?query=<키워드>&page=<n>
    → {"data":{"total_count":N,"recruits":[{id,title,company,annual,end_at,...}]}}
주의: 검색 파라미터는 q가 아니라 'query'다(q는 무시되고 전체 목록 반환).

신입 필터: annual.text ∈ {신입, 경력무관} 또는 annual.years==0 또는 제목에 '신입'.
회사 csn(사람인)은 없으므로 company_id는 빈 값.

사용 전: pip install curl_cffi   (미설치 시 자동 건너뜀)
주의: 약관/robots 준수, 매너 딜레이 유지. API 변경 시 조정 필요.
"""
import time
import urllib.parse

from config import COMMON_KEYWORDS, classify_str

BASE = "https://www.jobplanet.co.kr"
API = BASE + "/api/v3/job/postings"
NEWCOMER_TEXT = {"신입", "경력무관"}


def _is_newcomer(annual, title):
    if (annual.get("text") or "") in NEWCOMER_TEXT:
        return True
    if annual.get("years") == 0:
        return True
    return "신입" in (title or "")


def _deadline(end_at):
    """end_at(YYYY-MM-DD) → 'MM/DD'. 없거나 먼 미래(상시)는 '상시'/''."""
    if not end_at:
        return ""
    iso = str(end_at)[:10]
    if iso >= "2050-01-01":
        return "상시"
    return f"{iso[5:7]}/{iso[8:10]}" if len(iso) >= 10 else ""


def fetch_jobplanet(max_pages=3):
    try:
        from curl_cffi import requests as creq
    except ImportError:
        print("[잡플래닛] curl_cffi 미설치 → 건너뜀 (pip install curl_cffi)")
        return []

    s = creq.Session(impersonate="chrome")
    try:
        s.get(BASE + "/job/search", timeout=20)  # 쿠키 워밍업(Cloudflare __cf_bm)
    except Exception as e:
        print(f"[잡플래닛] 초기 접속 실패 → 건너뜀: {e}")
        return []
    headers = {"Accept": "application/json", "Referer": BASE + "/job/search"}

    all_rows, seen = [], set()
    for kw in COMMON_KEYWORDS:
        new = 0
        for page in range(1, max_pages + 1):
            url = API + "?" + urllib.parse.urlencode({"query": kw, "page": page})
            try:
                resp = s.get(url, headers=headers, timeout=20)
                if resp.status_code != 200:
                    print(f"    [잡플래닛] '{kw}' p{page} HTTP {resp.status_code}")
                    break
                recruits = (resp.json().get("data") or {}).get("recruits") or []
            except Exception as e:
                print(f"    [잡플래닛] '{kw}' p{page} 오류: {e}")
                break
            if not recruits:
                break
            for r in recruits:
                jid = str(r.get("id") or "").strip()
                title = (r.get("title") or "").strip()
                if not jid or not title or jid in seen:
                    continue
                if not _is_newcomer(r.get("annual") or {}, title):
                    continue
                seen.add(jid)
                comp = r.get("company") or {}
                all_rows.append({
                    "id": f"jp_{jid}",
                    "company_id": "",
                    "company": (comp.get("name") or "").strip(),
                    "role": title,
                    "category": classify_str(title),
                    "description": "",
                    "requirements": "신입",
                    "location": comp.get("city_name") or "",
                    "deadline": _deadline(r.get("end_at")),
                    "salary": "",
                    "source": "잡플래닛",
                    "url": f"{BASE}/companies/{comp.get('id')}/job_postings/{jid}" if comp.get("id") else "",
                })
                new += 1
            time.sleep(0.5)  # 매너 딜레이
        print(f"[잡플래닛] '{kw}': +{new}건")
    print(f"[잡플래닛] 총 {len(all_rows)}건 수집")
    return all_rows


if __name__ == "__main__":
    for r in fetch_jobplanet(max_pages=2)[:10]:
        print(r["category"], "|", r["company"], "|", r["location"], "|", r["deadline"], "|", r["role"][:30])
