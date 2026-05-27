# Spec 18 — 경로 상세 팝업 (Transit Route Detail)

**상태:** ✅ Implemented
**작성일:** 2026-05-27
**구현 브랜치:** hjkang83
**관련 spec:** 17 (apt-detail-modal), 02 (search-pipeline)

---

## 1. Why

- 카드에 "25분"만 표시되고 어떤 경로인지 알 수 없어 신뢰도 저하.
- `transit_routes` 테이블에 step1~5 상세 데이터(버스번호·지하철호선·출발역·도착역·소요시간)가 이미 저장돼 있음.
- `/api/apt/{apt_seq}/routes` 엔드포인트도 완성 상태 → **프론트엔드 UI만 추가**.
- 통근 경로를 직접 확인할 수 있으면 외부 앱(네이버지도·카카오맵) 이탈 감소.

---

## 2. User Story

```
As a 검색 결과를 보는 사용자,
I want to 카드의 통근시간 칩을 클릭해서 step-by-step 경로를 확인하고 싶고,
so that 어떤 지하철·버스를 타는지 직접 확인하고 출퇴근 경로를 판단할 수 있다.
```

---

## 3. Functional Requirements

- **F1**: 카드(추천·목록) 통근시간 칩 클릭 → 경로 상세 바텀시트 팝업 오픈
  - 카드 전체 클릭(단지 상세)과 이벤트 독립 (`event.stopPropagation()`)
- **F2**: `GET /api/apt/{apt_seq}/routes?wp_id={wp_id}` 호출 (기존 엔드포인트 재사용)
- **F3**: 경로 옵션 표시 (rank 순, 최적 경로 기본 펼침)
  - 각 step: 교통수단 아이콘(🚶/🚌/🚇) + 유형 + 노선명 + 출발역→도착역 + 소요시간
- **F4**: dual 모드 — W1/W2 탭 전환 (각 직장별 경로 표시)
- **F5**: 캐시 — `_routeCache` (동일 단지 재클릭 시 API 재호출 없음)
- **F6**: ESC 키 / 배경 클릭 / ✕ 버튼으로 닫기 (다른 모달보다 우선 닫힘)

---

## 4. Non-goals

- 카카오맵 경로 연동 (별도 spec)
- 실시간 소요시간 업데이트
- 보행 경로 지도 표시

---

## 5. Acceptance Criteria

- [x] AC1: 통근시간 칩 클릭 시 경로 팝업 오픈 (카드 클릭과 독립)
- [x] AC2: step별 교통수단 아이콘 + 노선 + 구간 + 소요시간 표시
- [x] AC3: 최적 경로(rank 1) 기본 펼침, 나머지 접힘
- [x] AC4: dual 모드 W1/W2 탭 전환
- [x] AC5: ESC / 배경 클릭 / ✕ 닫기 (route → detail → compare 순 우선)
- [x] AC6: `_routeCache` 캐시 동작 (API 재호출 없음)
- [x] AC7: 기존 테스트 회귀 없음

---

## 6. 구현 메모

> **구현 완료**: 2026-05-27

- `web/result.html` 만 수정 (백엔드 변경 없음):
  - CSS: `.route-overlay`, `.route-panel`, `.route-panel__wp-tabs` 등
  - HTML: `#route-overlay` 바텀시트 (`.detail-overlay` 위, z-index: 700)
  - JS: `openRoute()`, `closeRoute()`, `closeRouteOnBg()`, `_renderRoutePanel()`, `_routeOptionsHtml()`
  - `window._lastWpId2 = data.workplace_2?.wp_id || null` 저장 (dual 모드 지원)
  - 기존 `.dp-route` / `.dp-step` CSS 재사용
  - ESC 핸들러: route → detail → compare 순으로 닫힘 우선순위
