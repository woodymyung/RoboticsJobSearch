"""공통 설정: 검색 키워드, 사이트 우선순위, 직무 분류, 출력 경로.

== 수집 로직 ==
1) COMMON_KEYWORDS 로 여러 사이트(SITE_PRIORITY 순서)를 검색해 공고를 모은다.
2) 사이트 간 중복은 (회사명+직무명) 기준으로 제거하되, 우선순위 높은 사이트를 남긴다.
3) 각 공고 제목/직무분야를 classify()로 5개 직무로 분류한다.
"""
from pathlib import Path

# 신입 지원 가능 공고만: 사람인 exp_cd 1=신입
SARAMIN_EXP_CODES = ["1"]

# ▼ 공통 검색 키워드 — 모든 사이트에 동일하게 사용
#   핵심 8개 + 광역 키워드(스마트팩토리/자율주행/자동화설비)로 누락 방지.
#   ('자동화' 검색만으론 스마트팩토리 전용 공고가 페이지 밖으로 밀려 누락되므로 별도 추가)
COMMON_KEYWORDS = [
    "로봇", "로보틱스", "자동화", "휴머노이드",
    "머신비전", "협동로봇", "PLC", "ROS2",
    "스마트팩토리", "자율주행", "자동화설비",
]

# ▼ 사이트 우선순위 (앞에 있을수록 우선 — 중복 시 이 사이트 공고를 유지)
SITE_PRIORITY = ["사람인", "잡코리아", "잡플래닛"]


# ▼ 직무 5분류 — 우선순위 순으로 매칭(앞에서 잡히면 확정)
#   기획/PM   : 매니징·프로덕트/사업 기획·전략 (엔지니어링 아님)
#   영업      : 국내외 상품 영업·세일즈
#   필드엔지니어: 현장 시운전·설치·셋업·유지보수
#   생산/제조  : 실제 만드는 것 — 생산·제조·조립·양산
#   R&D       : 실제 엔지니어링 — 제어·개발·설계·연구·알고리즘
#
# ★ 다중 분류 허용: 한 공고가 여러 분류에 속할 수 있다.
#   특히 기획/PM은 1순위로, 엔지니어링 단어가 같이 있어도 기획/PM에 넣는다.
#   (예: "로봇 개발 PM" → 기획/PM + R&D 둘 다)
#   classify()는 분류 리스트를 반환한다. CSV엔 "기획/PM|R&D" 처럼 '|'로 저장.
def classify(text: str):
    t = text.replace(" ", "")
    cats = []

    # 영업
    if any(k in t for k in ["영업", "세일즈", "sales", "Sales", "B2B", "B2C", "수주", "해외영업", "기술영업"]):
        cats.append("영업")

    # 기획/PM (1순위) — 엔지니어링 단어가 같이 있어도 포함 (중복 허용)
    plan_kw = ["기획", "PM", "PO", "프로덕트", "product", "Product", "전략", "사업개발",
               "사업기획", "상품기획", "프로젝트매니저", "프로젝트리더", "BizDev",
               "매니저", "매니징", "매니지먼트", "운영기획", "운영관리"]
    if any(k in t for k in plan_kw):
        cats.append("기획/PM")

    # 필드엔지니어
    if any(k in t for k in ["시운전", "설치", "셋업", "세팅", "현장", "필드", "field", "Field",
                            "유지보수", "보전", "A/S", "AS", "티칭", "시공", "서비스엔지니어", "설비보전"]):
        cats.append("필드엔지니어")

    # 생산/제조/조립
    if any(k in t for k in ["생산", "제조", "조립", "양산", "가공", "공정", "오퍼레이터",
                            "operator", "품질관리", "QC", "QA", "검사", "생산기술", "공장"]):
        cats.append("생산/제조")

    # R&D — 제어·개발·설계·연구·알고리즘
    if any(k in t for k in ["개발", "설계", "제어", "엔지니어", "engineer", "연구", "알고리즘",
                            "SW", "HW", "FW", "펌웨어", "임베디드", "소프트웨어", "하드웨어", "R&D"]):
        cats.append("R&D")

    if not cats:
        cats = ["R&D"]  # 기본값
    # CATEGORIES 순서로 정렬 + 중복 제거
    return [c for c in CATEGORIES if c in cats]


def classify_str(text: str) -> str:
    """CSV 저장용: 분류 리스트를 '|'로 합침."""
    return "|".join(classify(text))


# 분류 라벨 목록 (UI 필터 노출 순서)
CATEGORIES = ["기획/PM", "R&D", "필드엔지니어", "생산/제조", "영업"]

# CSV 출력 경로 (HTML이 같은 폴더 상위에서 읽음)
_ROOT = Path(__file__).resolve().parent.parent
OUT_JOBS = _ROOT / "jobs.csv"
OUT_COMPANIES = _ROOT / "companies.csv"
OUT_CSV = OUT_JOBS  # 하위호환

# jobs.csv 스키마 — id(사람인 rec_idx)로 누적 관리, company_id(csn)로 회사와 매칭
JOB_COLUMNS = [
    "id",           # 사람인 공고 고유번호(rec_idx) — 누적/중복 관리 키
    "company_id",   # 회사 고유번호(csn) — companies.csv와 매칭 키
    "company",      # 회사명
    "role",         # 직무명
    "category",     # 분류
    "description",  # 직무 세부 설명
    "requirements", # 필수·우대 조건
    "location",     # 근무지
    "deadline",     # 마감일
    "salary",       # 연봉
    "source",       # 출처 사이트
    "url",          # 지원 링크
    "status",       # 모집중 / 마감 (이번 스크래핑에 없으면 마감 처리)
    "last_seen",    # 마지막으로 스크래핑에 잡힌 날짜(YYYY-MM-DD)
]

# companies.csv 스키마 — csn(id)로 누적 관리, 매출액은 DART로 보강
COMPANY_COLUMNS = [
    "id",           # 회사 고유번호(csn)
    "name",         # 회사명
    "revenue",      # 매출액 (DART OpenAPI)
    "employees",    # 사원수 (사람인)
    "founded",      # 설립 (사람인)
    "biz_type",     # 기업형태 (사람인)
    "industry",     # 업종 (사람인)
    "homepage",     # 홈페이지 (사람인)
    "last_updated", # 회사정보 갱신일(YYYY-MM-DD)
    "url",          # 사람인 기업정보 링크
]
COLUMNS = JOB_COLUMNS  # 하위호환
