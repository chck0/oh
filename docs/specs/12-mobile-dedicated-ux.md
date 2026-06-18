# Spec 12 — 모바일 전용 UX (지도↔리스트 전환 · 바텀시트)

**상태:** 📝 Draft
**작성일:** 2026-06-18
**관련 Spec:** 04 (result-page), 11 (rec-card-emphasis · 모바일 안전망), 36 (commute-first-map-ui)
**근거 문서:** `docs/premortem.md:64`, `web/static/design-system/COMPONENTS.md` §8.3

---

## 0. 최우선 원칙 (THE Constraint) — PC 무영향

> **이 스펙의 모든 작업은 PC(데스크톱) 코드를 한 줄도 수정하지 않고, 렌더링·동작에 어떤 영향도 주지 않는다.**

- 모바일 UX는 **오직 `@media (max-width: 767px)` 블록 안의 "추가" 규칙**으로만 구현한다.
- 기존 데스크톱 셀렉터(`.detail-panel`, `.chat-panel`, `.result-layout` 등)의 **기본 선언은 절대 수정/삭제하지 않는다.** 모바일에서 다르게 보여야 하면 미디어 쿼리에서 **덮어쓰기(override)** 만 한다.
- 모바일 전용 JS는 **`window.matchMedia('(max-width: 767px)')` 가드 뒤**에서만 동작하고, 데스크톱(≥768px)에서는 핸들러가 바인딩되지 않거나 즉시 `return` 한다.
- 새 DOM 요소(예: 모바일 토글 버튼)를 추가하더라도 **기본값 `display:none`** 으로 두어 데스크톱에서는 보이지도, 클릭되지도 않는다. 모바일 미디어 쿼리에서만 `display`를 켠다.
- **검수 기준:** `≥768px`에서의 시각/동작 diff = 0. 기존 테스트 회귀 0.

이 원칙과 충돌하는 요구가 생기면 **구현을 멈추고 질문한다.** (데스크톱을 건드려야만 풀리는 모바일 문제는 이 스펙 범위 밖)

---

## 1. Why

`docs/specs/11-rec-card-emphasis.md`는 모바일을 **"깨짐 방지용 세로 스택 안전망"** 까지만 처리하고, 모바일 **전용 인터랙션은 spec-12로 분리**한다고 명시했다(11번 5·37행). 그러나 spec-12 파일은 작성되지 않은 채(11 → 13으로 번호 건너뜀) 남아 있었다. 이 문서가 그 공백을 채운다.

`docs/premortem.md:64` — *"추가 조치 필요: 모바일 전용 UX 분리(지도 우선 / 리스트 우선 토글)."*

### 현재 모바일에서 실제로 깨지거나 부족한 것

| # | 증상 | 현재 코드 근거 |
|---|------|----------------|
| P1 | **상세 패널이 화면 밖으로 넘침** | `.detail-panel.open { width: 480px }` (result.html:1301) — 375~430px 뷰포트보다 넓음 |
| P2 | **친구 채팅 패널이 화면 밖으로 넘침** | `.chat-panel { position: fixed; width: 440px }` (result.html:1423) — 뷰포트 초과 |
| P3 | **지도↔리스트 초점 전환 불가** | 모바일은 `grid-template-rows: auto 50vh` 세로 고정(result.html:315~324). 지도/리스트 중 하나에 집중 불가 |
| P4 | **상세 정보가 바텀시트가 아님** | `COMPONENTS.md` §8.3은 "모바일 바텀시트(위로 스와이프 전체화면)"를 규정했으나 미구현 |

모바일 사용자(인터뷰에서 다수가 폰으로 매물 탐색)가 현 상태에서 상세/채팅을 열면 가로 스크롤·잘림이 발생한다.

**MANIFESTO 원칙:** "부동산 리포트가 아니다. 카톡 한 줄이다." — 모바일이 1차 화면이다.

---

## 2. Scope

### In-scope (전부 모바일 `<768px` 한정, 미디어 쿼리/가드 격리)
- **A. 상세 패널 모바일 바텀시트화** — `@media (max-width:767px)`에서만 `.detail-panel.open`을 전폭(100%) 또는 하단 시트로 override. 데스크톱 480px 사이드 패널은 그대로.
- **B. 채팅 패널 모바일 전폭화** — `@media`에서만 `.chat-panel`을 `width:100%`(또는 `100vw`)로 override. 데스크톱 440px 사이드 패널 그대로.
- **C. 지도↔리스트 토글(모바일 전용 버튼)** — 데스크톱 `display:none`, 모바일에서만 노출되는 플로팅 토글. "리스트 보기 / 지도 보기" 상태 전환(클래스 토글). 데스크톱 그리드·리사이즈(spec-19)에는 무영향.
- **D. 바텀시트 스와이프 닫기(선택, Phase 2)** — 아래로 드래그 시 닫힘. 모바일 터치 이벤트 한정.

### Out-of-scope (Non-goals)
- ❌ **데스크톱(≥768px) CSS/JS/HTML 변경** — 절대 불가 (§0)
- ❌ 백엔드 / API / DB 변경 — 순수 프론트, 기존 응답 필드만 사용
- ❌ 추천 카드 내용·칩 변경 — spec-11 소관, 그대로 둠
- ❌ 데스크톱 리사이즈 핸들(spec-19), 지도 정중앙 고정(spec-40) 로직 변경
- ❌ 별도 모바일 전용 라우트/HTML 파일 신설 — 같은 `result.html`에 미디어 쿼리로만
- ❌ 네이티브 앱 / PWA 매니페스트 — 범위 밖

---

## 3. 설계 (어떻게)

### 건드리는 파일
| 파일 | 변경 유형 | 무엇을 / PC 영향 |
|------|-----------|------------------|
| `web/result.html` | **추가만** | ① `@media (max-width:767px)` 블록에 A·B·C override 규칙 신규 추가 ② 모바일 토글 버튼 1개 DOM 추가(기본 `display:none`) ③ `matchMedia` 가드 JS 추가. **기존 데스크톱 규칙/JS 라인 수정 0** |
| `docs/specs/12-mobile-dedicated-ux.md` | 신규 | 이 문서 |

- **DB 변경:** 없음
- **API 변경:** 없음

### 격리 구현 패턴 (핵심)

```css
/* ❌ 이렇게 기존 데스크톱 선언을 고치지 않는다
   .detail-panel.open { width: 100%; }   ← 데스크톱까지 깨짐 */

/* ✅ 미디어 쿼리에서만 덮어쓴다 — 데스크톱 480px 선언은 무손상 */
@media (max-width: 767px) {
  .detail-panel.open {
    position: fixed; inset: auto 0 0 0;   /* 하단 바텀시트 */
    width: 100%; min-width: 0;
    height: 88vh; border-left: none;
    border-radius: 16px 16px 0 0;
    z-index: 900;
  }
  .chat-panel { width: 100%; min-width: 0; max-width: none; border-radius: 0; }
  .mobile-view-toggle { display: inline-flex; }   /* 기본 none → 모바일만 켬 */
}
```

```js
// ✅ 데스크톱에서는 바인딩조차 안 됨 → PC 동작 경로 무변경
const _mq = window.matchMedia('(max-width: 767px)');
function _bindMobileOnly() {
  if (!_mq.matches) return;            // 데스크톱이면 즉시 종료
  // 지도↔리스트 토글, 바텀시트 스와이프 등 모바일 전용 핸들러만 여기서
}
_mq.addEventListener('change', _bindMobileOnly);
_bindMobileOnly();
```

### C. 지도↔리스트 토글 동작 (모바일 전용)
- 기본 상태: 리스트 우선(카드 풀, 지도 축소) — 모바일 첫 진입은 "왜 추천인지"부터.
- 토글 클릭 → `.result-layout`에 **모바일 전용 클래스**(`.mobile-map-focus`) 추가/제거.
  - `@media (max-width:767px) .result-layout.mobile-map-focus { grid-template-rows: 0 100% }` 식으로 지도 우선.
  - 이 클래스 규칙도 **미디어 쿼리 안에만** 존재 → 데스크톱엔 정의 자체가 없어 무영향.
- 상태 저장: `localStorage`(선택). 없어도 동작.

### 핵심 주의 엣지케이스
- **`.result-layout` 자식 구조 불변** (GUIDE 함정: result.html 새 HTML 추가 시 grid 자식 영향). 토글 버튼은 grid 자식이 아니라 **`position:fixed` 플로팅**으로 띄워 grid 구조를 안 건드린다.
- **spec-19 리사이즈 핸들**은 이미 `@media (max-width:767px) .resize-handle { display:none }`(result.html:439)로 모바일에서 꺼져 있음 → 충돌 없음.
- **바텀시트 z-index**: 채팅(850)·상세와 겹치지 않게 정리. 지도 핀 오버레이보다 위.
- **iOS Safari 100vh 이슈**: `height:88vh` 대신 `100dvh` 계열 고려(동적 뷰포트). 데스크톱은 이 규칙을 안 받으므로 무관.

---

## 4. 완료 조건 (Acceptance Criteria)

### PC 무영향 (최우선 — 하나라도 실패 시 전체 실패)
- [ ] **AC0-a**: `≥768px`(데스크톱·태블릿)에서 기존과 **픽셀 동일** — 상세 480px 사이드 패널, 채팅 440px, 그리드/리사이즈 모두 변화 0
- [ ] **AC0-b**: 데스크톱 JS 실행 경로 변화 0 — 모바일 핸들러는 `matchMedia` 가드로 미바인딩
- [ ] **AC0-c**: 기존 전체 테스트 통과(회귀 0). 백엔드 변경 없음
- [ ] **AC0-d**: 추가된 모바일 토글 버튼이 데스크톱에서 `display:none`(보이지 않고 클릭 불가)

### 모바일 기능
- [ ] **AC1**: `≤767px`에서 상세 패널이 가로 넘침 없이 전폭/바텀시트로 표시
- [ ] **AC2**: `≤767px`에서 채팅 패널이 가로 넘침 없이 전폭으로 표시
- [ ] **AC3**: 모바일 토글로 리스트 우선 ↔ 지도 우선 전환 동작
- [ ] **AC4**: 375px / 390px / 430px 폭에서 가로 스크롤 발생 0
- [ ] **AC5**: (Phase 2) 바텀시트 아래로 스와이프 시 닫힘
- [ ] **AC6**: 데스크톱 Chrome + 모바일(실기기 또는 DevTools 디바이스 모드) 시각 검증 스크린샷 첨부

---

## 5. 알려진 제약 / 메모

- **실기기 검증**: spec-11과 동일하게 미디어 쿼리만으로는 실디바이스 동작 미확인 위험 — DevTools 디바이스 에뮬레이션 + 가능하면 실기기 1대 확인 권장.
- **단계화**: A·B·C(레이아웃·오버플로 해소 + 토글)를 Phase 1로, D(스와이프 제스처)를 Phase 2로 분리해 작은 PR로 진행. Phase 1만으로도 "넘침" 문제는 해소.
- **데스크톱 보호 회귀 테스트**: 구현 후 `≥768px` 스크린샷을 변경 전/후로 비교해 diff 0 확인하는 절차를 PR 체크리스트에 포함.
- 이 문서는 **Draft** — 구현은 사용자 승인 후 진행.
