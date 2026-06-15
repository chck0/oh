# Spec 38: 선택 단지 핀 강조 (지도에서 식별)

> 상태: Implemented | 작성일: 2026-06-15 | 브랜치: hjkang83

## 1. Why (왜)

- **문제:** 지도에서 아파트 핀을 클릭하면 ① 그 위치로 지도가 이동(panTo)하고 ② 상세 패널이 열리며 ③ 주변 POI 핀이 찍힌다. 그런데 **선택한 단지의 핀 자체는 주변 다른 단지 핀과 동일하게 보여서**, 화면이 이동하고 POI 핀까지 추가되면 "지금 내가 보고 있는 단지가 어느 핀이지?"를 한눈에 알 수 없다.
- **사용자가 얻는 것:** 선택한 단지 핀이 다른 핀과 확연히 구분되어, 지도 위에서 즉시 식별된다.

## 2. Scope (범위)

- **포함:**
  - 단지 상세가 열리면(`openDetail`=카드 클릭, `showDetail`=핀 클릭) **해당 단지 핀을 강조** 상태로 전환.
  - 강조 표현: 핀 확대(scale) + 흰색 외곽 링 + 글로우 그림자 + 최상단(zIndex) + 은은한 펄스 애니메이션.
  - 다른 단지로 전환하면 이전 강조 해제 후 새 단지 강조(항상 1개만).
  - 상세 패널을 닫으면(`closeDetail`/`backToList`) 강조 해제.
- **제외(안 함):**
  - 핀 색상 체계(통근시간 t1~t4·추천 best) 변경 — 기존 색은 유지하고 강조만 덧입힘.
  - POI 핀(`poi-custom-pin`)·직장 핀 표현 변경.
  - 백엔드/DB/API 변경.

## 3. 설계 (어떻게)

- **건드리는 파일:** `web/result.html` 뿐 (CSS `.pin-selected` + JS `setActiveAptPin`).
- **DB 변경:** 없음 · **API 변경:** 없음

- **CSS:** `.pin.pin-selected`
  - `transform: scale` 확대 + 가벼운 펄스(`@keyframes pinSelPulse`).
  - 흰색 외곽 링: `drop-shadow`를 상하좌우로 겹쳐 집 모양(지붕 삼각형 포함) 실루엣을 따라 흰 테두리 생성.
  - 강한 그림자 글로우로 떠 보이게.
  - `.pin:hover`보다 뒤에 선언(동일 specificity → source order로 우선).

- **JS:** `setActiveAptPin(aptSeq)`
  - 이전 강조 핀의 `.pin-selected` 제거 + 이전 오버레이 zIndex 원복.
  - `aptSeq`가 있으면 해당 핀 DOM(`.pin[data-apt-seq]`)에 `.pin-selected` 부여 + 오버레이 `setZIndex(높게)`.
  - 핀은 `aptOverlayMap[aptSeq]` CustomOverlay 콘텐츠로 DOM에 존재. 선택자 이스케이프 회피 위해 `data-apt-seq` 순회 비교.
  - `clearActiveAptPin()` = `setActiveAptPin(null)`.
  - 호출 지점: `openDetail`/`showDetail` 시작부에서 set, `closeDetail`/`backToList`에서 clear.

- **엣지케이스:**
  | 케이스 | 동작 |
  |---|---|
  | 추천(best)·복수평형 핀 선택 | 기존 색/왕관/뱃지 유지 + 강조 덧입힘 |
  | 관심단지 필터로 숨겨진 핀 | 숨김 상태면 강조 무의미(보이는 핀만 대상) |
  | 단지 A→B 전환 | A 해제 후 B만 강조 |
  | 패널 닫기 | 강조 해제 |

## 4. 완료 조건 (Acceptance Criteria)

- [x] AC1: 핀/카드 클릭으로 상세가 열리면 해당 단지 핀이 확대·흰 링·글로우·최상단으로 강조된다.
- [x] AC2: 다른 단지를 열면 이전 강조가 해제되고 새 단지만 강조된다(항상 1개).
- [x] AC3: 상세 패널을 닫으면 강조가 사라진다.
- [x] AC4: 핀 색상 체계(통근/추천)·POI 핀·직장 핀은 그대로다.
- [x] 순수 프론트(result.html) — 백엔드/DB/API 무변경.

## 5. Open Questions

- 없음 (시각 강조 한정, 데이터 영향 없음).
