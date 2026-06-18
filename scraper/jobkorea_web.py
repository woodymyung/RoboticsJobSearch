"""잡코리아 검색 스크래퍼 (requests + Next.js SSR JSON 파싱).

잡코리아 검색(/Search/)은 Next.js(RSC) 앱이라, 평범한 requests 요청으로 받은
HTML 안에 페이지당 20건의 구조화 JSON이 self.__next_f 플라이트 페이로드로
그대로 내장돼 있다. → Playwright/브라우저 없이 requests만으로 수집 가능.

확보 필드: legacyJobNo(상세 공고번호), title, companyName,
           careerType(1=신입·3=무관), applicationPeriod.end(마감일), areaCodeList(지역).
회사 csn은 잡코리아에 없으므로 company_id는 빈 값(사람인 기업정보와 직접 매칭 불가).

주의: 약관/robots 준수, 매너 딜레이 유지. 사이트 구조 변경 시 파서 조정 필요.
"""
import json
import re
import time
import urllib.parse
import requests

from config import COMMON_KEYWORDS, classify_str

BASE = "https://www.jobkorea.co.kr"
SEARCH = BASE + "/Search/"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
}
# 신입이 지원 가능한 careerType (1=신입, 3=신입·경력 무관)
NEWCOMER_CAREER = {"1", "3"}


def _decode_flight(html):
    """self.__next_f.push([1,"..."]) 청크들을 이어붙여 원본 RSC 문자열 복원."""
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', html, re.S)
    return "".join(json.loads('"' + c + '"') for c in chunks)


def _area_map(blob):
    """페이로드 area 패싯에서 지역코드→지명 + 부모코드 매핑 추출."""
    code2name, code2parent = {}, {}
    for code, parent, name in re.findall(
        r'\{"code":"([A-Z]\d{3})","parentCode":"([^"]*)","originName":"([^"]+)"', blob):
        code2name[code] = name
        code2parent[code] = parent
    return code2name, code2parent


def _location(area_codes, code2name, code2parent):
    """areaCodeList의 첫 코드를 '시/도 구/시' 형태 지명으로 변환."""
    if not area_codes:
        return ""
    code = area_codes[0]
    name = code2name.get(code, "")
    parent = code2parent.get(code, "")
    pname = code2name.get(parent, "")
    if pname and name and pname != name:
        return f"{pname} {name}"
    return name or pname


def _iter_job_objects(blob):
    """blob에서 legacyJobNo를 가진 JSON 객체를 중괄호 매칭으로 잘라 파싱."""
    for m in re.finditer(r'"legacyJobNo"', blob):
        s = blob.rfind("{", 0, m.start())
        if s < 0:
            continue
        depth = 0
        for j in range(s, len(blob)):
            ch = blob[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        yield json.loads(blob[s:j + 1])
                    except json.JSONDecodeError:
                        pass
                    break


def _search_one(session, query, max_pages):
    rows = []
    code2name = code2parent = None
    for page in range(1, max_pages + 1):
        params = {"stext": query, "careerType": "1", "Page_No": page}
        r = None
        for attempt in range(3):
            try:
                r = session.get(SEARCH, params=params, timeout=20)
                r.raise_for_status()
                break
            except Exception as e:
                print(f"    [잡코리아] '{query}' p{page} 재시도 {attempt+1}/3: {e}")
                time.sleep(2)
        if r is None:
            break
        blob = _decode_flight(r.text)
        if not blob:
            break
        if code2name is None:  # 지역 매핑은 한 번만 추출
            code2name, code2parent = _area_map(blob)
        jobs = list(_iter_job_objects(blob))
        if not jobs:
            break
        for o in jobs:
            if str(o.get("careerType", "")) not in NEWCOMER_CAREER:
                continue
            # 상세 URL(/Recruit/GI_Read/{no})은 'id' 필드를 사용한다.
            # (legacyJobNo는 별개 번호로 GI_Read에서 404가 난다)
            no = str(o.get("id") or "").strip()
            title = (o.get("title") or "").strip()
            if not no or not title:
                continue
            end = (o.get("applicationPeriod") or {}).get("end") or ""
            iso = end[:10] if end else ""
            # 잡코리아는 상시채용을 먼 미래 날짜(예: 2070-01-01)로 표기 → '상시'로 정규화
            if not iso:
                deadline = ""
            elif iso >= "2050-01-01":
                deadline = "상시"
            else:  # 사람인 표기(MM/DD)에 맞춰 통일 → 프론트 D-day 표시/정렬 호환
                deadline = f"{iso[5:7]}/{iso[8:10]}"
            rows.append({
                "id": f"jk_{no}",                       # 사람인 rec_idx와 충돌 방지 위해 접두어
                "company_id": "",                       # 잡코리아엔 사람인 csn 없음
                "company": (o.get("companyName") or "").strip(),
                "role": title,
                "category": classify_str(title),
                "description": "",
                "requirements": "신입",
                "location": _location(o.get("areaCodeList") or [], code2name or {}, code2parent or {}),
                "deadline": deadline,
                "salary": "",
                "source": "잡코리아",
                "url": f"{BASE}/Recruit/GI_Read/{no}",
            })
        time.sleep(0.5)  # 매너 딜레이
    return rows


def fetch_jobkorea(max_pages=3):
    """COMMON_KEYWORDS로 잡코리아 검색해 신입 공고 수집 (legacyJobNo 기준 중복 제거)."""
    s = requests.Session()
    s.headers.update(HEADERS)
    all_rows, seen = [], set()
    for kw in COMMON_KEYWORDS:
        try:
            got = _search_one(s, kw, max_pages)
        except Exception as e:
            print(f"[잡코리아] '{kw}' 오류 → 건너뜀: {e}")
            continue
        new = 0
        for r in got:
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            all_rows.append(r)
            new += 1
        print(f"[잡코리아] '{kw}': +{new}건")
    print(f"[잡코리아] 총 {len(all_rows)}건 수집")
    return all_rows


if __name__ == "__main__":
    rows = fetch_jobkorea(max_pages=1)
    for r in rows[:8]:
        print(r["category"], "|", r["company"], "|", r["location"], "|", r["role"][:30])
