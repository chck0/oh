# Spec: 준공연도 필터 (build_year_min)

> **상태**: Implemented ✅  
> **작성일**: 2026-05-25  
> **구현 브랜치**: hjkang83

---

## 1. Why (왜 만드는가)

- 실사용자 요구: "10년 이상 된 아파트는 보고 싶지 않아요" — 노후 단지를 자동 제외하고 싶다.
- 현재 파이프라인은 `is_apt=1 AND recent_trade=3` 조건만 있고, 준공연도 필터링이 없다.
- `apartments.build_year` 컬럼이 이미 존재하므로 추가 데이터 수집 없이 구현 가능.
- 검색 결과 품질 향상 + 사용자가 원하지 않는 구형 단지를 직접 필터링할 수 있게 됨.

---

## 2. User Story

```
As a 신축 아파트를 선호하는 사용자,
I want to  준공연도 기준으로 검색 결과를 필터링하고 싶다,
so that    2010년 이전 지은 구형 단지는 결과에서 아예 제외할 수 있다.
```

---

## 3. Scope

### In-scope
- `POST /api/search` 요청 파라미터에 `build_year_min: int | None` 추가
- 미지정 시 기존 동작 유지 (필터 없음)
- 백엔드 후보 단지 쿼리 + 카드 쿼리 양쪽에 `build_year >= ?` 조건 추가
- `result.html` UI에 "준공연도" 입력 필드 추가 (선택, placeholder: "예: 2010")
- 단위 테스트 + 파이프라인 통합 테스트

### Out-of-scope
- `build_year_max` (상한선): 요구 없음
- 준공연도 데이터 갱신 스크립트: 기존 `apartments.build_year` 그대로 사용
- 모바일 전용 UI: 기존 필터 패널 구조 그대로 활용

---

## 4. Functional Requirements

### F1. API 파라미터
```python
build_year_min: int | None = Field(
    None, ge=1960, le=2030,
    description="최소 준공연도. 예: 2010 → 2010년 이후 준공 단지만 반환."
)
```
- `None`(미지정) → 필터 없이 전체 반환 (하위 호환)
- 범위 위반(1960 미만 / 2030 초과) → 422 Unprocessable Entity

### F2. 백엔드 필터링 — 두 곳 적용

**F2-1. 후보 단지 쿼리** (Step 2, `apt_filter` 빌드)
```sql
-- build_year_min 지정 시 추가
AND build_year >= :build_year_min
```

**F2-2. 카드 쿼리** (Step 4, `min_cnt_clause` 패턴과 동일)
```sql
-- WHERE 절 끝에 추가
AND a.build_year >= :build_year_min   -- 지정 시만
```

### F3. UI — result.html 필터 패널

- 기존 "최소 세대수" 입력란 아래에 "준공연도 이후" 입력란 추가
- 숫자 입력 (type="number", min=1960, max=2030, placeholder="예: 2010")
- 빈 칸이면 파라미터 미포함 (필터 없음)
- 검색 폼 submit 시 `build_year_min` 값을 payload에 포함

---

## 5. Data Model

### 사용 컬럼 (기존)
```
apartments.build_year  INTEGER   -- 이미 존재, NULL 가능
```

- `build_year IS NULL`인 단지: `build_year_min` 지정 시 **제외** (NULL >= N 은 거짓)
- 데이터 갱신 불필요

### 신규 테이블/컬럼: 없음

---

## 6. Edge Cases

| 케이스 | 기대 동작 |
|--------|---------|
| `build_year_min` 미지정 | 기존 동작 그대로, 필터 없음 |
| `build_year IS NULL` 단지 | 필터 지정 시 결과에서 제외 |
| 필터 후 결과 0건 | 빈 `cards: []` + 200 반환 (기존 empty_response) |
| `build_year_min=1960` | 사실상 전체 포함 (최초 현대 아파트 기준) |
| 범위 위반 (예: 1900) | 422 Validation Error |

---

## 7. Acceptance Criteria

- [x] **AC1**: `build_year_min=2015` 전달 시 2015년 미만 준공 단지 카드 미포함 — `test_build_year_min_1960_with_matching_apt` 통과
- [x] **AC2**: `build_year_min` 미지정 시 기존 테스트 277개 모두 통과 (회귀 없음) — `test_no_filter_returns_card` 통과
- [x] **AC3**: `build_year_min=1900` 전달 시 422 반환 — `test_build_year_min_too_low_returns_422` 통과
- [x] **AC4**: `build_year IS NULL` 단지는 필터 지정 시 결과에서 제외 — `test_null_build_year_excluded_when_filter_set` 통과
- [x] **AC5**: result.html 필터 패널에 "준공연도 이후" 입력란 노출 — `web/search.html` ⑥ 섹션 추가

---

## 8. 구현 메모

> **구현 완료**: 2026-05-25 (Loop 3회)  
> **최종 테스트**: 282 passed (277 → +5, 회귀 0건)

### 변경된 파일

| 파일 | 변경 유형 | 내용 |
|------|---------|------|
| `app/search.py` | 수정 | `SearchRequest`에 `build_year_min` 필드 추가, Step2 `apt_filter` + Step4 카드 쿼리 양쪽에 `build_year_clause` 추가 |
| `web/search.html` | 수정 | ⑥ 준공연도 라디오 섹션 추가 (제한없음/2000/2010/2015/2020), 폼 submit 시 파라미터 포함 |
| `web/result.html` | 수정 | URL 파라미터 읽기 + 검색 조건 요약 표시에 `N년 이후` 노출 |
| `tests/test_search_pipeline.py` | 수정 | 422 검증 2개 + 필터 클래스 3개 (총 +5 테스트) |
| `docs/specs/07-build-year-filter.md` | 수정 | AC 체크 + 구현 메모 |

### 주요 결정 사항

1. **두 쿼리 모두 적용**: 후보 단지 쿼리(Step 2)와 카드 쿼리(Step 4) 양쪽에 필터 적용. 한 곳만 적용하면 통근 경로 조회는 됐지만 카드에서 제외되는 불일치가 발생함.
2. **NULL은 제외**: `build_year IS NULL` 단지는 필터 지정 시 자동 제외 (SQL 동작 그대로). 별도 처리 없음.
3. **라디오 버튼 선택**: 자유 입력(number input) 대신 연도 프리셋(2000/2010/2015/2020)으로 UX 단순화. 오입력 방지.
4. **하위 호환 유지**: `build_year_min=None` → 기존 쿼리 그대로, 회귀 없음.

### 알려진 제약

- `apartments.build_year` 데이터 미완성 시 필터 효과 제한. 실거래 데이터와 달리 준공연도는 수동 갱신 필요.
- AC5 실기기 UI 검증 미수행 (브라우저 직접 확인 필요).
