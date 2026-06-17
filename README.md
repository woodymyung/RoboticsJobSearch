# 로보틱스·자동화 신입 채용 수집기

채용 사이트에서 **로보틱스/자동화 신입 공고**를 분류별로 스크래핑해 표로 보여주는 도구.
데이터(`jobs.csv`)와 표현(`index.html`)을 분리했다 — 스크래퍼가 CSV를 만들고, HTML이 이를 읽어 렌더링한다.

```
JD/
├── jobs.csv              # 공고 데이터 (id=사람인 rec_idx 기준 누적 관리)
├── companies.csv         # 회사 데이터 (id=csn 기준, 매출액 등) — jobs와 company_id로 매칭
├── index.html            # 두 CSV를 불러와 join + 검색/필터/정렬/스크랩/숨김 UI
├── serve.py              # 로컬 서버 + '🔄 갱신' 버튼용 /scrape 엔드포인트
├── README.md
└── scraper/
    ├── config.py             # ★ 분류별 검색 키워드 + 우선순위 + CSV 스키마 (여기만 고치면 됨)
    ├── saramin_web.py        # 공고 스크래퍼 (requests+bs4, API 키 불필요·실동작)
    ├── saramin_company.py    # 기업정보 스크래퍼 (csn 기준 사원수/설립/업종 + DART 매출액)
    ├── jobkorea_playwright.py# 잡코리아 스크래퍼 (Playwright, 선택)
    ├── enrich_revenue.py     # DART OpenAPI로 매출액 보강 (선택)
    ├── build_csv.py          # 오케스트레이터 → ../jobs.csv, ../companies.csv 생성
    └── requirements.txt
```

## ID 기반 누적 관리 (핵심)

**전체 덮어쓰기가 아니라 ID 병합**이다. 갱신해도 찜/숨김(브라우저 localStorage) 기록은 보존된다.

- `jobs.csv` — 사람인 공고 고유번호 `rec_idx`를 `id`로 사용.
  - 이번 스크래핑에 잡힌 공고: `status=모집중`, `last_seen=오늘`로 갱신
  - 안 잡힌 기존 공고: **삭제하지 않고 `status=마감`으로 표시** → 찜해둔 공고가 마감돼도 계속 보임
- `companies.csv` — 회사 고유번호 `csn`을 `id`로 사용. 공고의 `company_id`와 매칭.
  - 신규 회사 또는 `COMPANY_REFRESH_DAYS`(기본 30일)보다 오래된 회사만 다시 조회 → 매번 전체 재조회 안 함
  - 매출액(`revenue`)은 **DART OpenAPI**로 보강. 사원수/설립/업종/홈페이지는 사람인 기업정보 페이지에서 파싱
- HTML이 두 CSV를 불러와 `company_id`로 join, 매출액·사원수·업종을 표에 함께 표시

---

## 1. 보기

`jobs.csv`에 수집 데이터가 들어있어 바로 볼 수 있다. 브라우저 보안상 `file://`로는 CSV 자동 로드가 막히므로 **로컬 서버로 여는 것을 권장**한다.

```bash
cd JD
python3 serve.py          # → http://localhost:8000
```

`serve.py`로 열면 '🔄 갱신' 버튼까지 동작한다. 단순 보기만 할 거면 `python3 -m http.server 8000` 도 가능(이 경우 갱신 버튼은 비활성).
정 안 되면 `index.html`을 그냥 열고 상단 **파일 선택**으로 `jobs.csv`를 직접 불러와도 된다.

### UI 기능
- **검색창**: 회사·직무·근무지·조건·출처 전체 텍스트 검색
- **분류 필터**: 기획/매니징 · R&D · 필드 엔지니어 · 제조 · 영업 · ⭐찜
- **마감일**: D-day 자동 계산, 7일 이내/임박 공고는 빨강 강조, 없으면 '상시/미정'
- **컬럼 정렬**: 헤더 클릭 (한 번 더 클릭 시 역순)
- **⭐ 스크랩(찜)**: 별을 누르면 브라우저(localStorage)에 저장 → 새로고침해도 유지. **찜 CSV 내보내기**로 따로 받기
- **🔄 갱신**: 스크래퍼를 다시 돌려 최신 공고로 교체 (serve.py 실행 중일 때만)

---

## 2. 데이터 갱신 (스크래핑)

### 방법 A — 버튼 갱신 (가장 쉬움)
`python3 serve.py`로 띄운 상태에서 페이지의 **🔄 갱신** 버튼 클릭.
내부적으로 `POST /scrape` → `scraper/build_csv.py` 실행 → `jobs.csv` 갱신 → 표 자동 리로드.

### 방법 B — CLI 직접 실행
```bash
cd JD/scraper
pip install -r requirements.txt          # requests, beautifulsoup4 (잡코리아 쓰면 playwright)
python3 build_csv.py                      # → ../jobs.csv 갱신
```

### (선택) 매출액 보강
채용 목록엔 매출액이 없어 비어 있다(HTML에선 '확인필요' 표시). DART 키를 넣으면 회사명으로 보강한다.
```bash
export DART_API_KEY=...                   # https://opendart.fss.or.kr 무료 발급
python3 build_csv.py
```

---

## 3. 분류 로직 — 검색 키워드 & 우선순위 (`scraper/config.py`)

분류는 **"분류마다 전용 검색어로 검색하고, 검색된 분류로 곧장 태깅"** 하는 방식이다.
사후에 제목 단어를 추정하지 않고 *검색 의도*로 분류하므로 정확도가 높다.

```python
# config.py
CATEGORY_QUERIES = {
    "영업":         ["로봇 영업", "자동화 기술영업", "로보틱스 세일즈", ...],
    "기획/매니징":  ["로봇 기획", "로보틱스 상품기획", "로봇 프로젝트 매니저", ...],
    "필드 엔지니어": ["로봇 시운전", "로봇 설치", "자동화 유지보수", "로봇 티칭", ...],
    "제조":         ["로봇 생산", "자동화설비 조립", "로봇 품질관리", ...],
    "R&D":          ["로봇 연구", "로보틱스 개발", "로봇 제어 알고리즘", ...],
}
```

- **검색어 = 사람인 검색창 입력값**. 공백은 AND 검색 (`"로봇 기획"` = 로봇 AND 기획).
- **딕셔너리 정의 순서 = 우선순위.** 한 공고가 여러 분류 검색에 동시에 잡히면 *위에 정의된* 분류로 확정된다.
  `build_csv.py`가 위에서부터 수집하고, `rec_idx`(사람인 공고 고유번호) 기준으로 중복 제거 시 **먼저 잡힌 것을 유지**하기 때문.
  → 더 좁고 명확한 분류를 위에 둘수록 정확해진다.
- **키워드/분류 수정은 이 딕셔너리만 고치면 된다.** 추가·삭제·순서변경 후 갱신하면 즉시 반영.

신입 필터는 사람인 `exp_cd=1`(신입)로 고정(`SARAMIN_EXP_CODES`).

### CSV 스키마
```
# jobs.csv
id, company_id, company, role, category, description, requirements,
location, deadline, salary, source, url, status, last_seen

# companies.csv
id, name, revenue, employees, founded, biz_type, industry, homepage, last_updated, url
```
`jobs.company_id` ↔ `companies.id` 로 매칭. 매출액은 companies.csv에만 있고 HTML이 join해서 보여준다.

---

## 4. 사이트별 스크래핑 전략 (왜 이렇게 했나)

| 사이트 | 방식 | 비고 |
|---|---|---|
| **사람인** | requests + BeautifulSoup | 검색결과가 서버 렌더링이라 적절한 User-Agent만으로 200 OK. **API 키 불필요·실동작 확인**. `exp_cd=1`로 신입만 |
| **잡코리아** | Playwright 헤드리스 (선택) | 공식 API 없음 + 403 빈번 + JS 렌더링. 미설치 시 자동 건너뜀. 셀렉터는 사이트 변경 시 수정 필요 |
| **잡플래닛** | (미구현) Playwright + 로그인 | 내부 JSON API가 로그인 게이트. 리뷰·연봉 보강용으로 확장 가능 |
| **리멤버** | 미지원 (수동) | 앱/로그인 전용 — 자동 스크래핑 비현실적·약관 위반 소지 |
| **매출액** | DART OpenAPI (선택) | 채용 데이터엔 매출 없음 → 회사명 → corp_code → 매출액 후처리 |

현재 기본 수집원은 **사람인**(약 1,100건 규모). 잡코리아는 `pip install playwright && playwright install chromium` 후 활성화된다.

---

## 5. 주의 / 한계
- 스크래핑은 각 사이트 이용약관·robots.txt를 따르고 요청 간 딜레이(`time.sleep`)를 유지한다. 대량/고빈도 요청은 차단·법적 리스크가 있다.
- **연봉**: 사람인 목록 페이지엔 대부분 없음('면접 후 결정') → '미기재'. 채우려면 각 공고 상세페이지 추가 스크래핑 필요.
- **매출액**: DART 키 미설정 시 비어 있음('확인필요').
- 공고는 수시 마감·변경되므로 **지원 전 원문 공고에서 마감일·자격요건을 반드시 재확인**할 것.
