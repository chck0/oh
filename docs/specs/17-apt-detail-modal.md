# Spec 17 — 단지 상세 모달 (Apartment Detail Modal)

**상태:** ✅ Implemented
**작성일:** 2026-05-27
**구현 브랜치:** hjkang83
**관련 spec:** 04 (result-page), 15 (search-history W2 수정 포함)

---

## 1. Why

- `GET /api/apt/{apt_seq}/detail` 엔드포인트가 이미 완성되어 있었지만 프론트엔드에서 전혀 호출되지 않았음.
- 카드 클릭 시 지도 이동만 되고 상세 정보 확인 방법이 없어 외부 앱(네이버·다음 부동산) 이탈 발생.
- 단지정보(준공·세대·주차·난방) + 최근 실거래 + 도보 POI를 BADUGI 안에서 완결.

---

## 2. User Story

```
As a 검색 결과를 보는 사용자,
I want to 카드를 클릭해서 단지 상세 정보를 바텀시트로 바로 보고 싶고,
so that 외부 앱을 열지 않아도 준공연도·주차·지하철·최근 거래를 한눈에 확인할 수 있다.
```

---

## 3. Functional Requirements

- **F1**: 카드(추천·목록) 클릭 → 지도 pan + 단지 상세 모달(바텀시트) 오픈
- **F2**: `GET /api/apt/{apt_seq}/detail?wp_id={wp_id}` 호출 (기존 엔드포인트 재사용)
- **F3**: 3개 탭 — 단지정보 / 시세·거래 / 주변시설
  - **단지정보**: 준공연도, 세대수, 최고층, 동 수, 주차, 전기차충전, 난방, 현관, 지하철, 6개월 시세요약
  - **시세·거래**: 최근 실거래 15건 (날짜·금액·평형·층)
  - **주변시설**: 도보권 POI 20개 (카테고리·이름·거리·도보시간)
- **F4**: 동일 단지 재클릭 시 캐시 활용 (추가 API 호출 없음)
- **F5**: 배경 클릭 / ESC 키 / ✕ 버튼으로 닫기
- **F6**: 모달 열릴 때 body scroll 잠금, 닫힐 때 복원

---

## 4. 추가 수정 (spec-15 버그픽스)

- **search.html W2 히스토리 칩**: 기존 칩이 W1(`address`)만 채웠던 버그 수정
  - W2 섹션(`#wp2-row`) 안에 `recent-searches-2` 컨테이너 추가
  - `loadRecentSearches()` → `_buildChipsHtml(items, targetId)` 헬퍼 분리
  - W2 칩 클릭 → `address2` 입력란 자동 채움

---

## 5. Non-goals

- 시세 차트 (Chart.js 의존성 추가 필요 — 별도 spec)
- 경로 상세 (spec-18 후보)
- 모달 내 즐겨찾기 버튼

---

## 6. Acceptance Criteria

- [x] AC1: 카드 클릭 시 바텀시트 모달 오픈
- [x] AC2: 단지정보 탭에 준공연도·세대수·주차·지하철 표시
- [x] AC3: 시세·거래 탭에 최근 실거래 내역 표시
- [x] AC4: 주변시설 탭에 도보 POI 표시
- [x] AC5: ESC / 배경 클릭 / ✕ 닫기 동작
- [x] AC6: 동일 단지 재클릭 시 캐시 (API 재호출 없음)
- [x] AC7: W2 히스토리 칩이 address2 입력란을 채움
- [x] AC8: 기존 테스트 회귀 없음

---

## 7. 구현 메모

> **구현 완료**: 2026-05-27

- `web/result.html`: `.detail-overlay` CSS + HTML + `openDetail()` / `closeDetail()` / `_renderDetail()` JS
  - `panToCard()` → `openDetail()` 위임 (하위호환 유지)
  - ESC 키 핸들러는 detail + compare 모달 공용
- `web/search.html`: `_buildChipsHtml(items, targetId)` 헬퍼 + `recent-searches-2` 컨테이너
