# Spec 16 — 가격 변동률 배지 (Price Change Badge)

**상태:** ✅ Implemented
**작성일:** 2026-05-27
**구현 브랜치:** hjkang83
**관련 spec:** 02 (search-pipeline), 04 (result-page), 06 (why-price-tag)

---

## 1. Why

- `trade_history` 테이블에 과거 거래 데이터가 이미 존재 — 추가 API 호출 없이 시세 변동 계산 가능.
- "지금 싼 건지 비싼 건지"를 직관적으로 알 수 없는 게 가장 큰 신뢰 장벽.
- 배지 하나로 "최근 3개월 vs 이전 6개월" 비교를 카드에 노출 → 검색 결과 신뢰도↑.

---

## 2. User Story

```
As a 재방문 사용자,
I want to 추천/목록 카드에서 최근 시세 변동을 배지로 한눈에 보고 싶고,
so that 외부 앱 없이 "지금 오르는 중인지 내리는 중인지" 즉시 판단할 수 있다.
```

---

## 3. Functional Requirements

- **F1**: `POST /api/search` 응답 카드에 `price_chg_6m_pct` 필드 추가 (nullable Float)
- **F2**: 계산 방식 — `trade_history` 배치 조회:
  - **최근값**: 최근 3개월 평균 실거래가 (거래 없으면 null)
  - **과거값**: 4~9개월 전 평균 실거래가 (거래 없으면 null)
  - **변동률** = `(recent_avg - past_avg) / past_avg × 100` (소수점 1자리)
  - |변동률| < 3% → null 반환 (노이즈 제거)
- **F3**: `result.html` 추천·목록 카드 가격 옆에 배지 표시
  - `price_chg_6m_pct >= 3`  → 🔺 `+N.N%` (빨간 배지)
  - `price_chg_6m_pct <= -3` → 🔻 `-N.N%` (파란 배지)
  - null → 배지 미표시
- **F4**: 즐겨찾기 비교 테이블에 "6개월 변동" 행 추가
- **F5**: trade_history 없거나 쿼리 실패 시 graceful degradation (배지 미표시)

---

## 4. Non-goals

- 실시간 시세 업데이트 (trade_history는 스크립트로 주기적 갱신)
- 1개월 미만 단기 변동 표시
- 특정 평형 이외 평형 개별 배지 (카드 표시 평형만 계산)

---

## 5. Acceptance Criteria

- [x] AC1: 카드 응답에 `price_chg_6m_pct` 필드 존재
- [x] AC2: 변동률 ±3% 미만은 null 반환
- [x] AC3: 상승 배지(🔺 빨간) / 하락 배지(🔻 파란) 카드에 표시
- [x] AC4: trade_history 없어도 500 없음 (graceful degradation)
- [x] AC5: 기존 테스트 회귀 없음

---

## 6. 구현 메모

> **구현 완료**: 2026-05-27

- `app/search.py`: `4d. price_chg_map` 배치 쿼리 추가 (tag_map 직후), `_card_to_dict`에 `price_chg_6m_pct` 추가
- `web/result.html`: `_priceChgBadge()` 함수 + CSS + 카드 렌더링 삽입 + 비교 테이블 "6개월 변동" 행
- `tests/conftest.py`: `trade_history`에 `deal_amount_int` 컬럼 추가
- `tests/test_price_change_badge.py`: 신규 테스트 (배치 계산, graceful degradation)
