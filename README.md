# 로보틱스·자동화 신입 채용 수집기

채용 사이트에서 **로보틱스/자동화 신입 공고**를 모아 직무별로 분류하고, 회사 규모(매출액·사원수)와 함께 표로 보여주는 도구.
데이터(CSV)와 표현(`index.html`)을 분리했다 — 스크래퍼가 CSV를 만들고, HTML이 이를 읽어 렌더링한다.

🔗 **데모(GitHub Pages)**: `https://woodymyung.github.io/RoboticsJobSearch/` (아래 *호스팅* 참고)

```
JD/
├── index.html            # 두 CSV를 불러와 join + 검색/필터/정렬/스크랩/숨김 UI
├── jobs.csv              # 공고 데이터 (id=사람인 rec_idx 기준 누적 관리)
├── companies.csv         # 회사 데이터 (id=csn 기준, 매출/사원수) — jobs와 company_id로 매칭
├── serve.py              # 로컬 서버 + '🔄 갱신' 버튼용 /scrape 엔드포인트
├── README.md
└── scraper/
    ├── config.py             # ★ 공통 검색 키워드 + 직무 분류 규칙 + CSV 스키마 (여기만 고치면 됨)
    ├── saramin_web.py        # 공고 스크래퍼 (requests+bs4, 키 불필요·실동작)
    ├── jobkorea_company.py   # 회사정보: 잡코리아 매출/사원수 + 사람인 fallback + DART 매출
    ├── saramin_company.py    # 사람인 기업정보 파서(csn 기준 사원수/설립/업종)
    ├── enrich_revenue.py     # DART OpenAPI 매출액 (회사명 100% 일치)
    ├── jobkorea_playwright.py / jobplanet_playwright.py   # 공고 멀티사이트(선택, Playwright)
    ├── build_csv.py          # 오케스트레이터 → ../jobs.csv, ../companies.csv 생성
    └── requirements.txt
```

---

## 1. 보기 (로컬)

CSV가 들어있어 바로 볼 수 있다. 브라우저 보안상 `file://`로는 CSV 자동 로드가 막히므로 **로컬 서버 권장**.

```bash
cd JD
python3 serve.py          # → http://localhost:8000
```

- `serve.py`로 열면 **🔄 갱신** 버튼까지 동작(스크래퍼 재실행).
- 단순 보기만 하면 `python3 -m http.server 8000` 도 가능(갱신 버튼은 비활성).
- 정 안 되면 `index.html`을 직접 열고 상단 **파일 선택**으로 `jobs.csv`를 불러와도 된다.

### UI 기능
- **검색창**: 회사·직무·근무지·조건·출처 전체 텍스트 검색
- **직무 필터**: 기획/PM · R&D · 필드엔지니어 · 생산/제조 · 영업 · ⭐찜 · 🚫숨김 (한 공고가 여러 직무에 동시 표시될 수 있음)
- **근무지 필터**: 시/도 단위 드롭다운
- **매출액 범위 필터**: ~50억 / 50~300억 / 300~1000억 / 1000억 이상 / 매출 미상
- **정렬**: 마감일·매출액·사원수 헤더 클릭(↑/↓ 토글). 값 없는 항목은 항상 뒤로
- **마감일**: D-day 자동 계산, 7일 이내 빨강 강조, 없으면 '상시/미정'
- **⭐ 스크랩(찜) / 🚫 숨김**: 브라우저(localStorage)에 저장 → 새로고침·재부팅해도 유지. **찜 CSV 내보내기** 가능
- **마감 공고**: 흐리게 + `마감` 뱃지. '마감 숨기기' 체크로 감출 수 있음
- **페이지네이션**: 페이지당 20건 + 하단 네비게이터

---

## 2. 호스팅 (GitHub Pages)

사이트는 **정적 파일**(`index.html` + CSV)이라 GitHub Pages에서 그대로 동작한다.
공개 데이터이므로 별도 백엔드 없이 호스팅 가능하다.

**활성화 (1회, 저장소 Settings):**
1. GitHub 저장소 → **Settings** → **Pages**
2. *Build and deployment* → Source: **Deploy from a branch**
3. Branch: **main** / 폴더: **/ (root)** → **Save**
4. 1~2분 후 `https://<사용자명>.github.io/RoboticsJobSearch/` 에 게시

**동작 / 한계**
- ✅ 보기·검색·필터·정렬·찜/숨김(localStorage) 전부 동작
- ❌ **🔄 갱신 버튼은 미동작** (정적 호스팅엔 백엔드가 없음). 데이터 갱신은 로컬에서 스크래핑 후 `git push`로 반영
- (선택) GitHub Actions로 주기적 자동 스크래핑+커밋도 가능 — 필요 시 추가

---

## 3. 데이터 갱신 (스크래핑)

### 방법 A — 버튼 갱신 (로컬, 가장 쉬움)
`python3 serve.py`로 띄운 상태에서 **🔄 갱신** 클릭 → `POST /scrape` → `build_csv.py` 실행 → 두 CSV 갱신 → 표 자동 리로드.

### 방법 B — CLI
```bash
cd JD/scraper
pip install -r requirements.txt          # requests, beautifulsoup4 (멀티사이트 쓰면 playwright)
python3 build_csv.py                      # → ../jobs.csv, ../companies.csv 갱신
```

### 매출액(DART) 키
매출액은 **DART OpenAPI**(공식 재무공시)로 채운다. 무료 키 발급: https://opendart.fss.or.kr → 인증키 신청.
```bash
# 둘 중 하나
export DART_API_KEY=발급키            # 환경변수, 또는
echo -n '발급키' > scraper/.dart_key   # gitignore된 파일(권장, 깃에 안 올라감)
```
키가 없으면 매출은 잡코리아 정확일치 값만, 그래도 없으면 '알 수 없음'으로 표시된다.

---

## 4. 수집·분류 로직 (`scraper/config.py`)

### 검색 — 공통 키워드 × 멀티사이트
```python
COMMON_KEYWORDS = ["로봇","로보틱스","자동화","휴머노이드","머신비전","협동로봇",
                   "PLC","ROS2","스마트팩토리","자율주행","자동화설비"]
SITE_PRIORITY   = ["사람인","잡코리아","잡플래닛"]   # 앞일수록 우선
```
- 모든 사이트를 공통 키워드로 검색(신입: 사람인 `exp_cd=1`).
- 사이트 간 중복은 `(회사명+직무명)` 기준 제거, **우선순위 높은 사이트** 공고를 유지.

### 직무 5분류 — 다중 허용
`classify()`가 제목/직무분야 키워드로 분류하며, **한 공고가 여러 직무에 속할 수 있다**(CSV엔 `기획/PM|R&D`처럼 `|`로 저장).
- **기획/PM** (1순위): 기획·PM·PO·전략·사업기획·매니징 등 (엔지니어링 단어가 같이 있어도 포함)
- **R&D**: 개발·설계·제어·연구·알고리즘·SW/HW/FW
- **필드엔지니어**: 시운전·설치·셋업·유지보수·티칭
- **생산/제조**: 생산·제조·조립·양산·품질·공정
- **영업**: 영업·세일즈·B2B·기술영업

예) `로봇 개발 PM` → `기획/PM` + `R&D` 둘 다. 키워드/분류 수정은 `config.py`만 고치면 된다.

### CSV 스키마
```
# jobs.csv
id, company_id, company, role, category, description, requirements,
location, deadline, salary, source, url, status, last_seen
# (salary는 사람인 목록에 거의 없어 UI에선 표시하지 않음)

# companies.csv
id, name, revenue, employees, founded, biz_type, industry, homepage, last_updated, url
```
`jobs.company_id`(=사람인 csn) ↔ `companies.id` 로 매칭. 매출/사원수는 companies.csv에만 있고 HTML이 join해 보여준다.

---

## 5. ID 기반 누적 관리

**전체 덮어쓰기가 아니라 ID 병합** — 갱신해도 찜/숨김(localStorage)·마감 공고가 보존된다.
- `jobs.csv`: 사람인 `rec_idx`를 `id`로. 이번에 잡힌 공고는 `status=모집중`·`last_seen=오늘`, 안 잡힌 기존 공고는 **삭제 않고 `status=마감`** → 찜한 공고가 마감돼도 계속 보임.
- `companies.csv`: 회사 `csn`을 `id`로. 신규 또는 `COMPANY_REFRESH_DAYS`(기본 30일) 지난 회사만 다시 조회 → 갱신이 빨라짐.

---

## 6. 사이트별 전략 / 한계

| 소스 | 방식 | 비고 |
|---|---|---|
| **사람인(공고)** | requests + bs4 | 서버 렌더링, 키 불필요·실동작. 기본 수집원 |
| **잡코리아/잡플래닛(공고)** | Playwright (선택) | JS·anti-bot. 미설치 시 자동 건너뜀. `pip install playwright && playwright install chromium` 후 활성화 |
| **매출액** | DART OpenAPI | 공식·정확. **회사명 100% 일치 + 동명이인 모호 시 제외**(오매칭 방지). 상장·외감기업 위주 |
| **사원수/규모/업종** | 잡코리아 + 사람인(csn) | 잡코리아 회사 프로필(매출/사원수) + 사람인 fallback(국민연금 사원수) |
| **리멤버** | 미지원 | 앱/로그인 전용 — 자동 스크래핑 비현실적 |

> ⚠️ 스크래핑은 각 사이트 약관·robots를 따르고 요청 간 딜레이를 유지한다. 공고는 수시 마감되므로 **지원 전 원문에서 마감일·자격요건을 재확인**할 것.
