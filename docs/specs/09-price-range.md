# Spec: 가격 범위 필터 (min_price)

> **상태**: Implemented ✅  
> **작성일**: 2026-05-25  
> **구현 브랜치**: hjkang83

---

## 1. Why (왜 만드는가)

- `max_price=10억` 검색 시 반경 내 거의 모든 아파트가 매칭 → 셀 수 폭증 → ODsay 타임아웃 504
- 현재는 가격 상한만 있고 하한이 없어 "1억~10억" 전체를 뒤짐
- `min_price` 추가 시 `deal_amount_int >= min_price` 조건으로 매칭 아파트·셀 수를 대폭 감소
- 예: "5억~10억" 검색 → 5억 미만 아파트 제외 → 셀 수 ~50% 감소 → 타임아웃 방지

---

## 2. User Story

```
As a 예산 범위가 정해진 사용자,
I want to  최소~최대 금액 범위를 직접 입력하고 싶다,
so that    예산 범위 밖 매물은 처음부터 제외되어 빠르고 정확한 결과를 볼 수 있다.
```

---

## 3. Scope

### In-scope
- `SearchRequest`에 `min_price: int | None` 추가 (선택, 기본 None = 하한 없음)
- `min_price` 지정 시 Step 2 + Step 4 쿼리 양쪽에 `deal_amount_int >= min_price` 조건 추가
- `min_price >= max_price` 시 422 Validation Error
- `search.html` ② 섹션: "최대 금액" → "가격 범위" 로 변경 (최소 + 최대 입력란)
- `result.html`: URL 파라미터 `min_price` 읽기 + API 요청 포함 + 검색 조건 요약 표시

### Out-of-scope
- 가격 슬라이더 UI (구현 복잡도 대비 효과 낮음)
- 프리셋 버튼 (자유 입력 방식으로 결정)
- 전세/월세 구분 필터 (별도 spec)

---

## 4. Functional Requirements

### F1. API 파라미터
```python
min_price: int | None = Field(
    None, ge=1000, le=2_000_000,
    description="최소 가격 (만원). 예: 30000=3억. 미지정=하한 없음."
)
```
- `None` → 기존 동작 유지 (하위 호환)
- `min_price >= max_price` → 422 Validation Error (field_validator)
- 범위 위반 → 422

### F2. 백엔드 필터링 — 두 곳 적용

**F2-1. Step 2 후보 단지 쿼리**
```sql
AND deal_amount_int >= :min_price   -- min_price 지정 시만
```

**F2-2. Step 4 카드 쿼리**
```sql
AND t.deal_amount_int >= :min_price  -- min_price 지정 시만
```

### F3. UI — search.html ② 섹션 변경

```
② 가격 범위

최소  [   ] 억  [     ] 만원   ← 신규 (선택, 비워두면 하한 없음)
최대  [ 5 ] 억  [  0  ] 만원   ← 기존 입력란 유지

최소 1억 이상 · 만원 칸은 천만 단위 (0, 1000, … , 9000)
최소 < 최대 이어야 합니다
```

- 최소 입력란: type=number, placeholder="제한없음"
- 최소가 비어 있으면 `min_price` 파라미터 미포함

### F4. result.html
- URL 파라미터 `min_price` 읽기 → API 요청 body에 포함
- 검색 조건 요약: `3억~10억` 형태로 표시

---

## 5. Edge Cases

| 케이스 | 기대 동작 |
|--------|---------|
| `min_price` 미지정 | 기존 동작 그대로 |
| `min_price >= max_price` | 422 |
| min_price 지정 후 결과 0건 | 빈 cards + 200 |
| min_price=1000 (1억) | 사실상 전체 포함 |

---

## 6. Acceptance Criteria

- [x] **AC1**: `min_price=30000, max_price=100000` 시 3억 미만 단지 카드 미포함
- [x] **AC2**: `min_price` 미지정 시 기존 테스트 282개 모두 통과 (회귀 없음 — 288개 통과)
- [x] **AC3**: `min_price >= max_price` 시 422 반환
- [x] **AC4**: search.html ② 섹션에 최소 금액 입력란 노출
- [x] **AC5**: result.html 검색 조건 요약에 `N억~M억` 형태 표시
- [x] **AC6(신규)**: 가격 범위 > 5억 시 경고 배너 표시 + 제출 차단

---

## 7. 구현 메모

> **구현 완료**: 2026-05-25  
> **테스트**: 288개 통과 (신규 6개 + 기존 282개 회귀 없음)  
> **브랜치**: hjkang83 → PR

### 추가 구현 (AC6)

| 항목 | 내용 |
|------|------|
| 경고 임계치 | `max_price - (min_price \|\| 0) > 50000` (5억 초과) |
| 경고 위치 | search.html ② 섹션 가격 입력 직하단 |
| 동작 | 입력 시 실시간 노란색 배너 표시, 제출 클릭 시 스크롤 + 차단 |

### 변경 파일 예정

| 파일 | 변경 유형 | 내용 |
|------|---------|------|
| `app/search.py` | 수정 | `min_price` 필드 추가, Step 2·4 쿼리 조건 추가, validator |
| `web/search.html` | 수정 | ② 섹션 최소 금액 입력란 추가, 유효성 검사 |
| `web/result.html` | 수정 | URL 파라미터 읽기 + 요약 표시 |
| `tests/test_search_pipeline.py` | 수정 | AC1·AC3 테스트 추가 |
| `docs/specs/09-price-range.md` | 수정 | AC 체크 + 구현 메모 |
