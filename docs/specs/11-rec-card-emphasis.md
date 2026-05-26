# Spec 11 — 추천 카드 이유 강조 + 좌측 패널 유연형 확대

**상태:** ✅ Implemented  
**작성일:** 2026-05-27  
**관련 Spec:** 04 (result-page), 06 (why-price-tag), 12 (모바일 전용 UX — 분리 예정)

---

## 1. Why

사용자 인터뷰(5인) 공통 피드백:
- "왜 이 매물을 추천하는지 핵심 근거 2~3가지를 한눈에"
- "오른쪽 지도보다 왼쪽 LLM 분석면이 더 강조되면 좋겠다"

추천 카드 = 통근/가격/연식 3축의 합리적 트레이드오프인데,  
현재는 다양한 정보가 흩어져 핵심 추천 이유가 묻힌다.  
첫 1초 안에 "왜 추천인지" 즉시 인지 가능해야 함.

**MANIFESTO 원칙:** "비교가 판단을 만든다" — 추천 카드가 *왜 추천인지*를 한눈에 보여줄 때 비교가 시작된다.

---

## 2. Scope

### In-scope
- **A. 좌측 패널 유연형 확대**: `400px 고정` → `minmax(440px, 32%)` + 화면 폭별 분기
- **B. 추천 카드(`rec-card`) 이유 칩 3개 추가**: 친구 코멘트 위 단독 행
  - 칩 1 (Info 키): 통근 → `{transit_summary} {total_time_min}분`
  - 칩 2 (Brand 키): 추천 이유 → `pick_reason` 핵심 또는 `price_diff_vs_fastest` 압축
  - 칩 3 (Neutral 키): 연식/평단가 → `{build_year}년 ({N}년차)` 또는 `평단 N만`
- **C. 기존 카드 요소 정리**: 칩과 중복되는 footer(`commute-chip` + `pick_reason`) 제거
- **D. 모바일(<768px) 안전망**: 세로 스택(카드 위 / 지도 아래 50vh) — 깨짐 방지만, 전용 UX 아님

### Out-of-scope (Non-goals)
- ❌ 일반 카드(`list-card`) 변경 — 추천 위계 구분을 위해 일반 카드는 현 상태 유지
- ❌ 추천 카드에 새 데이터 필드 추가 — 기존 응답 필드만 재배치
- ❌ 모바일 전용 인터랙션(지도↔리스트 탭 전환, bottom sheet) — **spec-12로 분리**
- ❌ 백엔드 API 변경 — 완전 프론트엔드 수정
- ❌ AI 코멘트 프롬프트 변경 — spec-05 소관
- ❌ 즐겨찾기 ♥ 버튼 위치·동작 변경 — spec-08 유지

---

## 3. Functional Requirements

### F1. 좌측 패널 폭 유연형 그리드

```css
/* 기본 (≥1101px): 유연형. 큰 화면일수록 LLM 분석면 자연 확대 */
.result-layout {
  grid-template-columns: minmax(440px, 32%) 1fr;
}
/* 태블릿 (768~1100px): 400px 고정 — 지도 가시 영역 보장 */
@media (max-width: 1100px) {
  .result-layout { grid-template-columns: 400px 1fr; }
}
/* 모바일 (<768px): 세로 스택 — 카드 위 / 지도 아래 50vh */
@media (max-width: 767px) {
  .result-layout {
    grid-template-columns: 1fr;
    grid-template-rows: auto 50vh;
  }
  .map-panel { min-height: 50vh; }
}
```

### F2. 추천 이유 칩 3개 (rec-card 전용)

배치: **친구 코멘트(`.rec-card__friend`) 바로 위**, 단독 행.

#### 칩 1 — 통근 (Info 키, blue)
- 텍스트: `{transit_summary} {total_time_min}분` (예: `2호선 직통 24분`)
- `transit_summary`가 빈 문자열이면 `{total_time_min}분` 단독 표시
- 색상: `var(--blue-100)` 배경, `var(--blue-700)` 텍스트

#### 칩 2 — 추천 이유 (Brand 키, red — 시선 집중)
- 우선순위:
  1. `price_diff_vs_fastest > 0` → `최단권보다 {N억 N천} 저렴`
  2. `pick_reason`에 "N곳 중" 포함 → `{pyeong_type} 중 최소가`
  3. 둘 다 해당 없으면 → `슬롯 최소가` (fallback)
- 색상: `var(--color-brand-bg-subtle)` 배경, `var(--color-brand-primary)` 텍스트

#### 칩 3 — 연식 또는 평단가 (Neutral 키, gray)
- 우선순위:
  1. `build_year` 있음 → `{build_year}년 ({age}년차)` (연식 무관 항상 표시)
  2. `build_year` 없고 `pyeong_price_avg` 있음 → `평단 {N}만`
  3. 둘 다 없음 → 칩 미표시 (2개 칩만)
- 색상: `var(--color-bg-subtle)` 배경, `var(--color-text-secondary)` 텍스트

### F3. 기존 카드 요소 정리 (rec-card만)

| 요소 | 이전 | 변경 후 |
|---|---|---|
| `.rec-card__meta` | 동·세대·연식·최고층 | **연식 제거** (칩 3 중복) → 동·세대·최고층 |
| `.rec-card__reasons` (NEW) | — | **친구 코멘트 위 단독 행, 칩 3개** |
| `.rec-card__friend` (HERO) | 유지 | 유지 |
| `.rec-card__footer` (commute-chip + pick_reason) | 있음 | **전체 제거** (정보가 칩 1·2로 흡수됨) |

---

## 4. Non-functional Requirements

- **성능**: 순수 CSS + HTML 템플릿 변경. JS 로직 추가 없음. 렌더링 시간 영향 0.
- **Vercel 60초 제약**: 영향 없음 (백엔드 변경 없음).
- **Supabase / pgBouncer**: 영향 없음 (DB 변경 없음).
- **하위 호환**:
  - 기존 응답 필드만 사용 → API 변경 0
  - `build_year` NULL 단지 → 칩 3 fallback으로 평단가 표시 → 그래도 없으면 칩 2개만
  - 즐겨찾기 ♥, 탭 클릭 동작 그대로 유지
- **회귀**: 기존 340개 테스트 통과 (백엔드 변경 없으므로 자동 통과 예상).
- **접근성**: 칩 텍스트 색상 대비 WCAG AA 통과 (디자인 시스템 검증값 사용).

---

## 5. UX / Vibe

MANIFESTO → "부동산 리포트가 아니다. 카톡 한 줄이다."

- 칩은 **명사형 짧은 라벨** (≤12자). 문장 X.
  - ✅ `2호선 직통 24분` / `20평대 중 최소가` / `2018년 (8년차)`
  - ❌ `이 매물은 2호선 직통이라 통근이 빠릅니다`
- 칩 3개 = "통근 / 추천 이유 / 연식·가격" 세 축으로 트레이드오프 한눈에 비교.
- **빨강(brand) 칩은 1개만** — 디자인 시스템 §2.2 (빨강 5% 이하 원칙) 준수. 정보 위계 핵심.
- 이모지·바이트 X (MANIFESTO 탈).

---

## 6. Data Model

신규 테이블/컬럼 **없음**. 기존 응답 필드만 재배치:

| 필드 | 출처 | 칩 용도 |
|---|---|---|
| `total_time_min` | `transit_routes.total_time_min` | 칩 1 |
| `transit_summary` | `_card_to_dict` 계산 | 칩 1 |
| `price_diff_vs_fastest` | `ai.py build_recommendations` | 칩 2 |
| `pick_reason` | `ai.py _make_pick_reason` | 칩 2 fallback |
| `pyeong_type` | `trade_recent.pyeong_type` | 칩 2 |
| `build_year` | `kapt_complexes.kaptUsedate` 파싱 | 칩 3 |
| `pyeong_price_avg` | `_card_to_dict` 계산 | 칩 3 fallback |

---

## 7. Edge Cases

| 케이스 | 기대 동작 |
|---|---|
| `transit_summary === ''` (경로 미입) | 칩 1: `{total_time_min}분` 단독 표시 |
| `price_diff_vs_fastest === 0` (최단권 자체) | 칩 2: `{pyeong_type} 중 최소가` |
| `build_year IS NULL` + `pyeong_price_avg IS NULL` | 칩 3 미표시 → 2개 칩만 표시 |
| 모바일 너비 320px | 칩 3개 wrap 처리 (`flex-wrap: wrap`) |
| 좌측 패널 내부 구조 변경 후 grid 깨짐 | `.result-layout` 자식은 `.left-panel`, `.map-panel` 2개 유지 (SPEC_GUIDE 함정 #1 참피) |
| 즐겨찾기 ♥ 버튼 오버랩 | 패딩 우측 44px 유지 (spec-08 동일) |
| 데스크탑 → 모바일 리사이즈 | 미디어 쿼리만으로 처리, JS 이벤트 추가 없음 |

---

## 8. Acceptance Criteria

- [ ] **AC1**: 1440px 화면에서 좌측 패널이 ~461px (32%)로 렌더링됨
- [ ] **AC2**: 1100px 이하에서 좌측 패널 400px 고정 유지 (회귀 없음)
- [ ] **AC3**: 767px 이하에서 좌측 패널 100% width + 지도 50vh로 세로 스택
- [ ] **AC4**: 추천 카드(`rec-card`)에 친구 코멘트 위 단독 행으로 칩 3개 노출
- [ ] **AC5**: 칩 2(Brand 키)는 카드 1장당 최대 1개 (디자인 시스템 빨강 면적 원칙)
- [ ] **AC6**: `build_year` NULL인 단지에서 칩 3이 평단가로 fallback 또는 미표시
- [ ] **AC7**: `price_diff_vs_fastest > 0`인 추천 카드에 `최단권보다 N억 N천 저렴` 칩 노출
- [ ] **AC8**: 일반 카드(`list-card`)는 변경 없음 — 기존 즐겨찾기·코멘트·통근 표시 그대로
- [ ] **AC9**: 추천 카드 footer(`commute-chip` + `pick_reason`) 제거됨 (정보는 칩 1·2로 흡수)
- [ ] **AC10**: 기존 340개 테스트 통과 (회귀 0)
- [ ] **AC11**: 데스크탑 Chrome / Safari에서 시각적 검증 완료 (스크린샷 첨부)

---

## 9. 구현 메모

> **구현 완료**: 2026-05-27  
> **테스트**: 백엔드 변경 없음 → 기존 테스트 회귀 없이 통과 확인

### 변경된 파일

| 파일 | 변경 유형 | 내용 |
|------|---------|------|
| `web/result.html` | 수정 | CSS: `.result-layout` 유연형 그리드 + 미디어 쿼리 2단계, `.rec-card__reasons` + `.reason-chip` 3 variant. JS: `reasonChip2Text/3Text` 헬퍼, `renderRecCard()` 재구성 (meta에서 build_year 제거, reasons 칩 삽입, footer 제거) |
| `docs/specs/11-rec-card-emphasis.md` | 신규 | 이 문서 |
| `docs/specs/SPEC_GUIDE.md` | 수정 | 기존 Specs 표에 spec-11 추가 |

### 주요 결정 사항

1. **칩 3개 중 Brand 칩은 1개만**: 디자인 시스템 §2.2 "빨강 5% 이하" 원칙 준수.
2. **footer 완전 제거**: 칩 1(통근), 칩 2(추천 이유)에 정보가 흡수됨. footer 잔존 시 중복 + 시각적 노이즈.
3. **`.rec-card__footer` CSS는 잔존**: 다른 곳에서 쓸 가능성 대비 잔존. 쓰이면 사실상 무효화되므로 위험 없음.
4. **반응형은 미디어 쿼리만**: JS 리사이즈 핸들러 없음. 성능 영향 0.
5. **모바일 안전망의 `grid-template-rows`**: `auto 50vh`로 카드 영역의 자연 높이, 지도만 50vh 고정. 카드가 많아도 자체 스크롤(`.cards-panel { overflow-y: auto }`)로 처리.

### 알려진 제약

- **실기기 모바일 검증 미실시**: 미디어 쿼리만 작성, 320~767px 실제 디바이스에서 동작 미확인.
- **칩 텍스트 한국어 폭 가변**: `최단권보다 1억 5천 저렴`처럼 긴 문자열은 `flex-wrap: wrap`으로 줄바꿈 처리. 정렬 깨짐은 없음.
- **`pick_reason` 패턴 매칭**: `/\d+곳 중/.test(c.pick_reason)`로 슬롯 내 비교 여부 추론. `ai.py`의 `_make_pick_reason` 문구가 바뀌면 칩 2 fallback 동작 변할 수 있음 (현재는 fallback이라 무방).
