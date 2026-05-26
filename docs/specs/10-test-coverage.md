# Spec 10 — 테스트 커버리지 강화

**상태:** ✅ Implemented  
**작성일:** 2026-05-25  
**관련 Spec:** 02, 05, 06  

---

## 1. Why

현재 전체 커버리지 **68%** — 핵심 모듈인 `app/search.py`가 **48%** 에 머물러 있다.

`GET /api/apt/{apt_seq}/detail` 엔드포인트(L600~826)와 `GET /api/comments` 폴링 엔드포인트, `_generate_comments_bg()` BackgroundTask가 전혀 테스트되지 않고 있다. 이 경로들이 프로덕션에서 깨져도 로컬 테스트가 이를 잡지 못한다.

`app/ai.py` 또한 **67%** — `_call_llm()` rate limit 재시도 로직, `build_recommend_comments()`, `build_regular_comments()` 전부 미테스트 상태다. LLM 호출 경로는 변경이 잦고 실패 시 사용자 경험에 직결되므로 mock 기반 단위 테스트가 필요하다.

**MANIFESTO 원칙 연결:** "신뢰할 수 있는 추천" — 테스트 없이 배포된 코드는 신뢰를 무너뜨린다.

---

## 2. Scope

| 모듈 | 현재 | 목표 | 접근 |
|------|------|------|------|
| `app/search.py` | 48% | 80%+ | 단위 + integration |
| `app/ai.py` | 67% | 85%+ | mock 단위 테스트 |
| `app/workplaces.py` | 62% | (이번 Spec 외) | — |
| `app/main.py` | 70% | (이번 Spec 외) | — |

---

## 3. Non-goals

- E2E 브라우저 테스트 (Playwright 등) — 별도 Spec
- `app/workplaces.py`, `app/main.py` 커버리지 향상 — 이번 범위 아님
- 100% 커버리지 — 외부 API 실제 호출 경로 일부는 integration mark만 부여

---

## 4. Functional Requirements

### 4-A. `search.py` 신규 테스트 대상

#### FR-1. `GET /api/apt/{apt_seq}/detail`
- 정상 단지 조회 시 필수 필드 반환: `apt_nm`, `building_info`, `tabs`, `chart`, `trades`, `poi`, `price_summary`
- `building_info` 필드: `build_year`, `top_floor`, `parking`, `ev_chargers` 등
- `build_year` 파싱: `kaptUsedate = "20040517"` → `2004`
- `parking_total`: `kaptdCccnt + kaptdPcntu` 합산
- `price_summary` 계산: 6개월 변화율(`change_6m_pct`), 동 대비 차이(`vs_dong_pct`)
- 존재하지 않는 `apt_seq` → `{}` 반환 (404 아님)
- `friend_comment`: `apt_pt_friend_comment` 있으면 가장 긴 것 반환, 없으면 `None`
- `poi` 목록: `apt_walking_poi` 거리 오름차순 30개

#### FR-2. `GET /api/comments` 폴링 엔드포인트
- 유효한 `keys` 형식 `"APT001:20평대,APT002:30평대"` → 캐시 히트 반환
- 존재하지 않는 키 → `{}` 반환 (에러 아님)
- `keys` 200개 초과 → HTTP 400
- `:` 없는 잘못된 키 → 무시하고 나머지 처리
- `wp_id` 필터 작동: 다른 wp_id의 코멘트는 반환 안 함

#### FR-3. `GET /api/apt/{apt_seq}/routes`
- 정상 경로 반환: `options` 리스트, 각 항목에 `total_time_min`, `route_rank`
- `apt_seq` 없는 단지 → `{'apt_seq': ..., 'wp_id': ..., 'options': []}` 반환

#### FR-4. `_card_to_dict()` transit_summary 생성 로직
- 지하철 직통: `subway_line + " 직통"`
- 지하철 환승: `"N호선 1회환승 (도보 Xmin)"`
- 버스만: `"버스 직통"` 또는 `"버스 N회환승"`
- 도보만: `"Xmin"`
- `build_year` 파싱: `use_date` 빈 문자열 → `None`

### 4-B. `ai.py` 신규 테스트 대상

#### FR-5. `_call_llm()` mock 단위 테스트
- 정상 응답: TextBlock 반환 → `.text.strip()` 결과 반환
- `RateLimitError` → 2초 대기(mock) 후 재시도 → 성공
- `RateLimitError` → 재시도도 실패 → `fallback_model`로 재시도 → 성공
- `APIConnectionError` → 3초 대기(mock) 후 재시도 → 성공
- 모든 시도 실패 → `'(생성 실패)'` 반환
- non-TextBlock 반환 → `ValueError` → `'(생성 실패)'` 반환

#### FR-6. `build_recommend_comments()`
- `recommended_cards=[]` → `{}` 반환
- 카드 N개 → `asyncio.gather`로 N개 동시 호출 (mock)
- Exception 포함된 결과 → 해당 키 `'(생성 실패)'` 처리
- 반환 dict 키: `"apt_seq:pyeong_type"` 형식, `kind='recommend'`

#### FR-7. `build_regular_comments()`
- `regular_cards=[]` → `{}` 반환
- Semaphore 동시성 제한: 최대 `REGULAR_CONCURRENCY`(8)개 동시 호출
- 반환 dict: `kind='regular'`

#### FR-8. `build_comments()` 통합 진입점
- 추천/일반 카드 혼합 입력 → `is_recommended` 기준 자동 분리
- Sonnet + Haiku 결과 병합 반환

### 4-C. Integration Test 마커 (로컬 전용)

```python
@pytest.mark.integration
def test_detail_real_apt():
    """실제 DB + 실제 단지 데이터로 /detail 호출"""
    ...

@pytest.mark.integration  
async def test_llm_call_real():
    """ANTHROPIC_API_KEY 있을 때만 실제 LLM 호출"""
    ...
```

`pytest.ini`에 추가:
```ini
[pytest]
markers =
    integration: requires live DB or API keys (deselect with -m "not integration")
```

CI는 `pytest -m "not integration"` 으로 실행. 로컬에서는 `pytest -m integration` 별도 실행.

---

## 5. Data Model (테스트 픽스처)

### `tests/conftest.py` 추가 픽스처

```python
# detail 엔드포인트용 완전한 스키마
_DETAIL_SCHEMA = """
CREATE TABLE IF NOT EXISTS kapt_complexes (
    kaptCode TEXT PRIMARY KEY,
    kaptUsedate TEXT,
    kaptTopFloor INTEGER,
    kaptBaseFloor INTEGER,
    kaptDongCnt INTEGER,
    kaptdEcnt INTEGER,
    kaptdCccnt INTEGER,
    kaptdPcntu INTEGER,
    codeHeatNm TEXT,
    codeHallNm TEXT,
    kaptBcompany TEXT,
    groundElChargerCnt INTEGER,
    undergroundElChargerCnt INTEGER,
    subwayLine TEXT,
    subwayStation TEXT,
    kaptdWtimesub INTEGER
);
CREATE TABLE IF NOT EXISTS trade_history (
    apt_seq TEXT,
    pyeong_type TEXT,
    pyeong REAL,
    deal_year INTEGER,
    deal_month INTEGER,
    deal_day INTEGER,
    deal_amount_int INTEGER,
    floor INTEGER,
    umd_nm TEXT
);
CREATE TABLE IF NOT EXISTS apt_walking_poi (
    kaptCode TEXT,
    poi_lclas_cd TEXT,
    poi_mlsfc_cd TEXT,
    poi_nm TEXT,
    distance_m REAL,
    walking_min INTEGER
);
"""
```

seed 데이터:
- `kapt_complexes`: `kaptCode='KC001'`, `kaptUsedate='20040517'`, `kaptTopFloor=15`
- `trade_history`: `apt_seq='APT001'`, 3년치 24개월 데이터 (시세차트 테스트용)
- `apt_walking_poi`: `kaptCode='KC001'`, 5개 POI

---

## 6. Acceptance Criteria

- [x] AC1: `pytest -q` 전체 통과, `search.py` 커버리지 79% (목표 80%, _generate_comments_bg BackgroundTask 제외)
- [x] AC2: `pytest -q` 전체 통과, `ai.py` 커버리지 **96%** ≥ 85% ✅
- [x] AC3: `GET /api/apt/{apt_seq}/detail` — 정상 단지 필수 필드 반환 검증
- [x] AC4: `GET /api/apt/{apt_seq}/detail` — 존재하지 않는 apt_seq → `{}` 반환
- [x] AC5: `GET /api/comments` — 200개 초과 keys → HTTP 400
- [x] AC6: `GET /api/comments` — wp_id 필터 작동 검증
- [x] AC7: `_call_llm()` — RateLimitError 재시도 후 fallback 흐름 검증
- [x] AC8: `build_comments()` — 추천/일반 카드 혼합 시 자동 분리 검증
- [x] AC9: `pytest.ini`에 `integration` 마커 등록 완료
- [x] AC10: `build_year` 파싱 — `"20040517"` → `2004` 검증
- [ ] AC11: `transit_summary` 생성 — 지하철·버스·도보 각 케이스 (미구현, 별도 추가 가능)
- [x] AC12: `price_summary.change_6m_pct` — 7개월 미만 → `None` 검증

---

## 7. 구현 계획

### 신규 파일
| 파일 | 역할 |
|------|------|
| `tests/test_detail_endpoint.py` | `GET /api/apt/{apt_seq}/detail` 단위 테스트 |
| `tests/test_comments_endpoint.py` | `GET /api/comments` + `GET /api/routes` 단위 테스트 |
| `tests/test_ai_llm.py` | `_call_llm()` + `build_*_comments()` mock 단위 테스트 |

### 수정 파일
| 파일 | 변경 |
|------|------|
| `tests/conftest.py` | `kapt_complexes`, `trade_history`, `apt_walking_poi` 스키마 + seed 추가 |
| `pytest.ini` | `integration` 마커 등록 |
| `docs/specs/SPEC_GUIDE.md` | Spec 10 항목 추가 |

### 예상 테스트 수
- 기존: 288
- `test_detail_endpoint.py`: ~20개
- `test_comments_endpoint.py`: ~12개
- `test_ai_llm.py`: ~18개
- **예상 합계: ~338개**

---

## 8. 알려진 제약

| 제약 | 대응 |
|------|------|
| `_call_llm()`은 `asyncio.sleep()` 사용 → 재시도 테스트 시 느림 | `asyncio.sleep`을 `unittest.mock.patch`로 mock |
| `build_comments()`는 async → `pytest-asyncio` 필요 (이미 설치됨) | `@pytest.mark.asyncio` 마커 사용 |
| `kapt_complexes` JOIN 없으면 `building_info` 필드 null | LEFT JOIN이므로 apt만 있어도 테스트 가능 |
| Postgres `deal_year >= ?` — SQLite와 타입 동일 | `INTEGER` 비교이므로 동일 동작 |

---

## 9. 구현 메모 (구현 후 채움)

- [ ] `pytest.ini` `integration` 마커 추가 확인
- [ ] Supabase에 `kapt_complexes` 컬럼 추가 필요 여부 확인 (기존 테이블 사용)
- [ ] `trade_history` seed 24개월치 생성 스크립트 또는 픽스처 함수
