# Spec 14 — 즐겨찾기 단지 나란히 비교 (Favorites Compare)

**상태:** ✅ Implemented
**작성일:** 2026-05-27
**구현 브랜치:** hjkang83
**관련 spec:** 08 (favorites), 04 (result-page), 11 (rec-card-emphasis)

---

## 1. Why

- 사용자가 ♥ 즐겨찾기로 단지를 저장하지만, "A 단지 vs B 단지 어느게 나아?"라는 질문에 답하는 UI가 없음.
- 현재 유일한 해결책: 외부 앱(호갱노노 등) 이탈 → 신뢰 손실.
- `cards` 데이터(통근시간, 가격, 세대수, 연식, 저가근거)는 이미 응답에 포함 → **API 변경 없이** 프론트엔드만으로 구현 가능.

---

## 2. User Story

```
As a 즐겨찾기 탭을 사용하는 사용자,
I want to 저장된 단지 중 2~3개를 선택해 나란히 비교하고,
so that 외부 앱으로 이탈하지 않고 BADUGI 안에서 최종 결정을 내릴 수 있다.
```

---

## 3. Functional Requirements

- **F1**: ♥ 관심 탭에서 각 카드에 체크박스 노출 (전체 탭에는 미표시)
- **F2**: 2개 이상 선택 시 하단 바에 "N개 선택됨 · 비교하기" 버튼 활성화
- **F3**: 최대 3개 선택. 4번째 체크 시 무시 (체크 되지 않음)
- **F4**: "비교하기" 클릭 → 오버레이 비교 테이블 표시
- **F5**: 비교 항목: 단지명, 평형, 통근시간, 최저 실거래가, 세대수, 연식, 최고층, 저가 근거
- **F6**: dual 모드 시 통근시간 → `W1 N분 · W2 N분`
- **F7**: 오버레이 닫기 (✕ 버튼 또는 배경 클릭)
- **F8**: 탭 전환("전체") 시 비교 선택 초기화 + 하단 바 숨김
- **F9**: 백엔드 변경 없음, API 변경 없음

---

## 4. Acceptance Criteria

- [x] AC1: 관심 탭에서 체크박스 노출
- [x] AC2: 2개 미만 선택 시 "비교하기" 비활성
- [x] AC3: 3개 초과 선택 불가
- [x] AC4: 비교 테이블에 6개 이상 비교 항목 표시
- [x] AC5: dual 모드 통근시간 올바르게 표시
- [x] AC6: 오버레이 배경 클릭 시 닫힘
- [x] AC7: 전체 탭 전환 시 비교 초기화
- [x] AC8: 기존 테스트 360개 전체 통과 (회귀 없음)

---

## 5. 구현 메모

> **구현 완료**: 2026-05-27

- 백엔드/API 변경 없음 — result.html 단독 변경
- `compareSet: Map<id, card>` — 선택 상태 관리
- `renderListCard(c, wpId, cmpMode)` / `renderRecCard(c, wpId, cmpMode)` — cmpMode=true 시 체크박스 추가
- `switchFavTab('fav')` 렌더 시 cmpMode=true 전달
- 비교 오버레이: `.compare-overlay` + `.compare-table` (CSS Grid 테이블)
- `clearCompare()` — 탭 전환 시 자동 호출
