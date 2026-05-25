# Spec: Why-tagged 추천 카드 — 저가 근거 자동 태깅

> **상태**: Implemented ✅  
> **작성일**: 2026-05-25  
> **구현 브랜치**: hjkang83/why-price-tag  
> **관련 파일**: `BADUGI_pipeline_stages.md` (파이프라인 다이어그램)

---

## 1. Why (왜 만드는가)

- MANIFESTO 원칙: **"비교가 판단을 만든다"** — 최저가 카드는 가격 그 자체가 아니라 *왜 싼지*를 보여줄 때 비교가 완성된다.
- 사용자가 얻는 가치: 카드를 받은 뒤 다른 앱으로 이탈해 교차검증하는 행동을 차단. "1억 싼 데는 이유가 있다"는 불신이 "알고 싸다"는 신뢰로 전환.
- 인터뷰 근거: **5인 전원 일치 요구** (2026-05 인터뷰). 유일하게 전원 합의된 항목.
- Why Tree 연결: 타겟 범위(좁히기/넓히기) 전략과 무관하게 적용 가능한 보편 개선 → ROI 최우선.

---

## 2. User Story

```
As a 부동산을 한두 번 알아본 30대 1인 가구,
I want to 추천 카드에서 "왜 이 가격인지" 한 줄로 바로 확인하고 싶다,
so that 다른 앱을 열지 않아도 "알고 싸다"는 확신을 갖고 임장 여부를 결정할 수 있다.
```

---

## 3. Scope

### In-scope
- 추천 카드 1장당 저가 근거 태그 1~2개 자동 생성
- 태그 대상: 층수 (저층/고층), 직전 거래 대비 변동률
- 데이터 소스: 공공 API 3종 (실거래가 + 건축물대장 + 공동주택 단지목록)
- 태그가 생성 불가한 경우 카드는 태그 없이 정상 노출 (graceful degradation)
- SQLite(로컬) + Supabase Postgres(Vercel) 양쪽 동작

### Out-of-scope (Non-goals)
- **향(북향/동향)**: 공공 API에 호·동 단위 방향 정보 없음. 추후 건축물대장 상세 파싱 시 재검토.
- **동 위치(도로변/단지 내측)**: 위성 좌표 처리 필요 → Phase 2.
- **호가 기반 태그**: MANIFESTO 원칙 위반 (실거래 기준만 사용).
- **사설 데이터 연동**: 공공데이터 원칙 유지.
- **LLM 생성 태그**: 결정론적 규칙으로만 생성, LLM 호출 없음.

---

## 4. Functional Requirements

### F1. 데이터 파이프라인 — 3단계 수집·가공

**F1-1. 1단계: 원본 데이터 수집**

| API | 수집 항목 | 용도 |
|-----|---------|-----|
| 국토교통부 실거래가 | 거래일, 가격, 층, 전용면적, 단지명, 주소 | 모든 태그의 입력값 |
| 건축HUB 건축물대장 | 단지 최고층(지상), 사용승인일, 동 수 | 층수 분류 기준값 |
| 공공데이터포털 공동주택 단지목록 | 단지 ID(kapt_code), 좌표, 주소 | 단지 매칭 키 |

**F1-2. 2단계: 가공 및 태그 원자 계산**

- **단지 매칭**: 실거래가의 `단지명 + 지번주소` → `kapt_code` 매핑 (기존 `apartments` 테이블의 `kaptCode` 활용)
- **층수 분류**: `거래 층 / 단지 최고층` 비율로 라벨링

  | 비율 | 라벨 | 표시 문구 |
  |-----|------|---------|
  | ≤ 0.15 | `저층` | "저층 매물" |
  | 0.15 ~ 0.30 | `1층대` | "1층대 매물" |
  | ≥ 0.85 | `고층` | "고층 매물" |
  | 나머지 | (태그 없음) | — |

  > 1층 정확히: `층 == 1` → `"1층 매물"` (비율 계산보다 우선 적용)

- **변동률 계산**: 동일 `(단지, 평형타입)` 그룹 내 직전 거래가 대비 현재 거래가 차이

  ```
  변동률 = (현재_거래가 - 직전_거래가) / 직전_거래가 × 100
  ```
  - `|변동률| < 3%` → 태그 생략 (노이즈 제거)
  - `변동률 ≤ -5%` → `"직전 거래 대비 -N%" 태그 표시`
  - `변동률 ≥ +5%` → `"최근 N% 상승" 태그 표시`
  - 직전 거래가 없거나 6개월 초과 → 태그 생략

**F1-3. 3단계: 추천 엔진 내 태그 결합**

현재 추천 파이프라인 순서:
1. 통근시간 필터링 (`transit_cache + transit_routes`)
2. 예산 필터링 (`deal_amount_int <= max_price`)
3. 단지별 최저 실거래가 추출 (`MIN(deal_amount_int)`)
4. **[신규]** 2단계 태그를 카드 응답에 결합

### F2. 카드 응답 스키마 — `why_tags` 필드 추가

`POST /api/search` 응답의 `cards[]` 각 항목에 `why_tags` 필드 추가:

```json
{
  "apt_nm": "A아파트",
  "pyeong_type": "20평대",
  "price_low": 73000,
  "total_time_min": 25,
  "why_tags": [
    { "type": "floor",    "label": "1층 매물",         "detail": "단지 평균 대비 -7%" },
    { "type": "price_chg","label": "직전 거래 대비 -5%", "detail": "6개월 내 기준" }
  ]
}
```

- `why_tags`는 빈 배열 `[]` 가능 (태그가 없을 때)
- `type`: `"floor"` | `"price_chg"` (향후 확장 가능한 enum)
- `label`: UI에 직접 표시하는 한국어 문구 (최대 12자)
- `detail`: 툴팁 또는 서브텍스트용 보조 설명 (선택, null 가능)

### F3. UI — 추천 카드 태그 표시

- 카드 가격 아래에 `저가 근거: [태그1] · [태그2]` 형식 1줄 노출
- 태그 최대 2개. 3개 이상이면 우선순위: `floor` > `price_chg`
- 태그가 없으면 해당 줄 미노출 (레이아웃 변화 없음)
- 예시 최종 카드:

  ```
  은평구 A아파트 24평
  7억 3천만 원 · 상암 출근 25분
  저가 근거: 1층 매물 · 직전 거래 대비 -7%
  ※ 최근 실거래 기준 (호가 아님)
  ```

### F4. 데이터 파이프라인 스크립트

- `scripts/tag_price_reason.py`: 기존 `trade_recent` 테이블에서 태그 원자 계산 → `trade_tags` 테이블에 저장
- 주기: 실거래가 갱신 스크립트(`scripts/fetch_trades.py`) 실행 후 연속 실행

---

## 5. Non-functional Requirements

- **성능**: 태그 계산은 검색 요청 시점이 아닌 **사전 파이프라인**에서 완료. API 응답 시간에 영향 없음.
- **Vercel 60초 제약**: 영향 없음 (검색 시 DB 조인만 추가).
- **데이터 정합성**: 직전 거래 없거나 데이터 부족 시 태그 생략, 오류 미발생.
- **보안**: 공공 API 키는 환경변수 관리. 태그 계산에 사용자 입력 미포함.
- **모바일**: 태그 줄은 1줄 고정. 넘치면 말줄임표 처리.

---

## 6. UX / Vibe

MANIFESTO 톤: **"부동산 잘 아는 친구가 카톡으로 귀띔해주는" 한 줄**

- 톤: 데이터 보고서가 아닌 귀띔. `"저층 매물이에요"` X → `"1층 매물"` O (명사형, 간결)
- "저가 근거" 레이블은 "싸다"를 강조하지 않고 "이유 있다"는 뉘앙스
- ※ 표기: `최근 실거래 기준 (호가 아님)` — 데이터 출처 명시로 신뢰 강화
- 에러/태그 없음: 줄 자체를 미노출. "정보 없음" 메시지 노출 금지.

---

## 7. Data Model

### 신규 테이블: `trade_tags`

```
trade_tags
├── apt_seq:       TEXT    -- apartments.apt_seq FK
├── pyeong_type:   TEXT    -- '20평대' 등 평형 구분
├── tag_type:      TEXT    -- 'floor' | 'price_chg'
├── label:         TEXT    -- UI 표시 문구 (≤12자)
├── detail:        TEXT    -- 보조 설명 (nullable)
├── base_trade_id: INTEGER -- 계산 기준이 된 trade_recent.id
├── calc_date:     TEXT    -- 태그 계산 시각 (ISO 8601)
└── PRIMARY KEY (apt_seq, pyeong_type, tag_type)
```

### 영향받는 기존 테이블

| 테이블 | 변경 내용 |
|-------|---------|
| `trade_recent` | 변경 없음 — `deal_amount_int`, `floor`, `deal_year`, `deal_month` 기존 컬럼 활용 |
| `kapt_complexes` | 변경 없음 — `kaptTopFloor` 기존 컬럼 활용 |
| `apartments` | 변경 없음 — `kaptCode` FK로 `kapt_complexes` 조인 |

---

## 8. API / Interface

### 8-1. 검색 응답 변경 (`POST /api/search`)

```python
# app/search.py — _card_to_dict() 에 why_tags 필드 추가
def _card_to_dict(r, recent_map, tag_map):
    ...
    return {
        ...
        'why_tags': tag_map.get((r['apt_seq'], r['pyeong_type']), []),
    }
```

태그 조회:
```sql
-- 카드 apt_seq 목록으로 배치 조회 (단일 쿼리)
SELECT apt_seq, pyeong_type, tag_type, label, detail
FROM trade_tags
WHERE apt_seq IN ({ph})
```

### 8-2. 파이프라인 스크립트

```python
# scripts/tag_price_reason.py

def calc_floor_tag(apt_seq: str, floor: int, top_floor: int) -> dict | None:
    """층수 태그 계산. 태그 없으면 None."""

def calc_price_chg_tag(apt_seq: str, pyeong_type: str, conn) -> dict | None:
    """직전 거래 대비 변동률 태그 계산. 6개월 이내 직전 거래 없으면 None."""

def run(conn):
    """trade_recent + kapt_complexes → trade_tags 전체 재계산."""
```

실행:
```bash
python scripts/tag_price_reason.py          # 전체 재계산
python scripts/tag_price_reason.py --since 2026-04  # 특정 월 이후만
```

---

## 9. Edge Cases

| 케이스 | 기대 동작 |
|---|---|
| `kaptTopFloor` NULL | 층수 태그 생략. 카드 정상 노출. |
| 직전 거래 없음 (신규 단지) | 변동률 태그 생략. |
| 직전 거래가 6개월 초과 | 변동률 태그 생략 (오래된 기준은 노이즈). |
| `\|변동률\| < 3%` | 태그 생략 (의미 없는 변동). |
| `why_tags` 3개 이상 | 우선순위 적용: `floor` > `price_chg`. 최대 2개만 응답. |
| Supabase 연결 실패 | 기존 검색 결과 정상 반환 + `why_tags: []`. |
| 스크립트 실행 중 API 오류 | 해당 단지 건너뜀, 로그 기록, 나머지 계속 처리. |

---

## 10. Acceptance Criteria

구현 완료 판단 기준:

- [x] **AC1**: `trade_tags` 테이블 생성 마이그레이션 스크립트 존재 — `scripts/supabase_schema.sql` 추가
- [x] **AC2**: `scripts/tag_price_reason.py` 실행 후 `trade_tags`에 데이터 삽입됨 — `run()` 함수 + CLI 구현
- [x] **AC3**: `POST /api/search` 응답 `cards[].why_tags`에 태그 포함 (데이터 있을 때) — `test_why_tags_has_seeded_label` 통과
- [x] **AC4**: 태그 없는 카드에서 `why_tags: []` 반환, UI 해당 줄 미노출 — graceful degradation + `_whyTagsHtml()` 빈 배열 처리
- [x] **AC5**: 1층 매물은 `"1층 매물"` 태그, 고층(≥85%)은 `"고층 매물"` 태그 표시 — `calc_floor_tag()` 구현 + 12개 단위 테스트 통과
- [x] **AC6**: 직전 거래 대비 -5% 이하 → `"직전 거래 대비 -N%"` 태그 표시 — `calc_price_chg_tag()` 구현 + 13개 단위 테스트 통과
- [x] **AC7**: `※ 최근 실거래 기준 (호가 아님)` 문구 카드 하단 노출 — 기존 `web/result.html` 템플릿에 포함 (기존 구현 유지)
- [x] **AC8**: 로컬(SQLite) + Vercel(Supabase) 양쪽 환경에서 동작 — `upsert_sql()` + `USE_PG` 분기로 양쪽 지원
- [x] **AC9**: 기존 테스트 244개 전부 통과 (회귀 없음) — 277 passed (회귀 0건)
- [ ] **AC10**: 모바일(375px)에서 태그 줄 잘림 없이 1줄 표시 — CSS 적용 완료, 실기기 검증 미수행 (섹션 12 알려진 제약 참고)

---

## 11. Open Questions

- **Q1**: `trade_tags` 재계산 주기를 어떻게 트리거할 것인가? (GitHub Actions cron / Vercel cron / 수동)
- **Q2**: 고층 태그(`≥85%`)는 긍정 신호인데 "저가 근거" 레이블과 함께 노출하면 혼란하지 않을까? → 별도 `"가격 특이점"` 레이블 분리 검토 필요.
- **Q3**: `변동률` 기준이 되는 "직전 거래"를 동일 층/동으로 좁혀야 하는가, 단지 전체 평균으로 넓혀야 하는가?
- **Q4**: 향후 태그 타입 확장(`재건축_연한`, `학군`) 시 `tag_type` enum 관리 방법.

---

## 12. 구현 메모

> **구현 완료**: 2026-05-25  
> **최종 테스트 결과**: 277 passed (기존 244 → +33, coverage 43% → 68%)

### 변경된 파일

| 파일 | 변경 유형 | 내용 |
|------|---------|------|
| `scripts/tag_price_reason.py` | 신규 | 순수 함수 + DB run() + CLI 진입점 |
| `tests/test_why_tags.py` | 신규 | 순수 함수 30개 단위 테스트 |
| `scripts/supabase_schema.sql` | 수정 | `trade_tags` 테이블 DDL 추가 |
| `tests/conftest.py` | 수정 | `_SCHEMA` 끝에 `trade_tags` DDL 추가 |
| `tests/test_search_pipeline.py` | 수정 | `_FULL_SCHEMA`에 `trade_tags` 추가, seed 데이터 추가, AC 테스트 3개 추가 |
| `app/search.py` | 수정 | `tag_map` 배치 조회 블록 추가, `_card_to_dict` `why_tags` 필드 추가 |
| `web/result.html` | 수정 | `.why-tags` CSS, `_whyTagsHtml()` JS 함수, 추천/리스트 카드 템플릿 삽입 |
| `docs/specs/06-why-price-tag.md` | 수정 | 이 섹션 작성 |

### 주요 결정 사항

1. **`base_trade_id` 컬럼 생략**: Spec 7절 데이터 모델에는 `base_trade_id` 컬럼이 있었으나, 구현 시 불필요한 복잡성으로 판단해 제외. PK `(apt_seq, pyeong_type, tag_type)` 으로 단일 진실 보장.

2. **사전 계산 방식 유지**: 검색 요청 시 태그를 실시간 계산하지 않고 `scripts/tag_price_reason.py`로 사전 계산 후 `trade_tags` 테이블에 저장. 검색 파이프라인에서는 배치 `SELECT`만 수행 → API 응답 시간 영향 제로.

3. **Graceful degradation**: `trade_tags` 조회 시 `try/except` 래핑. 테이블 미존재 또는 쿼리 실패 시 `why_tags: []`로 조용히 반환. 이전 배포 환경과의 호환성 보장.

4. **임계값 구현 차이**: Spec 4절 F1-2에는 `|변동률| < 3%`라고 명시했으나, 구현에서는 `|변동률| < 5%`로 적용 (±5% 이상만 태그 생성). Spec 텍스트가 초안 단계의 불일치였으며, 실제 코드와 테스트는 5% 기준으로 통일.

5. **aioresponses 0.7.8 호환**: `match_querystring=False` 파라미터 미지원. 테스트에서 `re.compile(re.escape(URL))` 패턴으로 우회.

6. **SQLite `check_same_thread=False`**: FastAPI async 핸들러는 이벤트 루프 전용 스레드에서 실행되므로, 테스트용 in-memory SQLite 연결에 반드시 필요.

7. **`upsert_sql()` 재사용**: `app/portable.py`의 기존 헬퍼로 SQLite `INSERT OR REPLACE` ↔ Postgres `ON CONFLICT DO UPDATE` 양쪽 지원.

### 알려진 제약

- **`trade_tags` 재계산 주기 미정 (Q1)**: 현재 수동 실행만 가능. GitHub Actions cron 연동은 Phase 2.
- **고층 태그와 "저가 근거" 레이블 혼용 (Q2)**: 고층 매물이 오히려 프리미엄인데 "저가 근거"로 묶이는 UX 모순 잠재. UI 레이블 분리 미결.
- **AC10 미검증**: 모바일 375px 실기기 레이아웃 테스트 미수행 (CSS `white-space:nowrap; overflow:hidden; text-overflow:ellipsis` 적용으로 깨짐 방지만 구현).
- **Supabase camelCase 컬럼**: `kaptTopFloor` 등 camelCase 컬럼은 `app/db.py`의 `_CAMEL_COLS` 처리에 의존. `trade_tags`는 snake_case 전용이므로 문제 없음.
