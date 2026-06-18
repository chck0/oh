# Spec 44: 브랜드 색상 테마 — 핑크-퍼플 그라데이션 시스템

> 상태: Implemented | 작성일: 2026-06-18 | 커밋: 911c5ae

## 1. Why (왜)

- 기존 단색 핑크(`#pink-500`)는 CTA 버튼 간 시각적 위계가 약하고 다크 테마와 어울리지 않음
- 다크 배경(`#0d0d0d`) 위에서 벽돌빨강 그림자(`rgba(168,46,27,*)`)가 색상 충돌을 유발
- 핑크→퍼플 그라데이션으로 교체해 브랜드 일관성 강화 + 다크 테마와의 조화 목표

## 2. Scope (범위)

**포함:**
- `tokens.css` — 브랜드 그라데이션 시맨틱 토큰 신규 정의
- `search.html` — 분석하기 버튼, 활성 칩(통근시간), 배우자 직장 추가 버튼
- `result.html` — 결과 보기 버튼, 채팅 전송 버튼
- 다크 모드: 구 벽돌빨강 그림자 → 보라 글로우 일괄 교체

**제외(안 함):**
- 지도 핀 색상 (통근시간 정보 의미가 있어 유지)
- 텍스트 색, 배경 색, 테두리 색 체계 (변경 없음)

## 3. 설계 (어떻게)

### 건드린 파일
- `web/static/design-system/tokens.css`
- `web/search.html`
- `web/result.html`

### DB 변경
없음

### API 변경
없음

### 토큰 정의 (`tokens.css`)

```css
/* 원색 그라데이션 */
--grad-accent: linear-gradient(120deg, #FF6FB5 0%, #C45ED6 50%, #7C3FE6 100%);

/* 시맨틱 CTA 토큰 */
--color-brand-gradient:       var(--grad-accent);
--color-brand-gradient-hover: linear-gradient(120deg, #FF7FC0 0%, #CB6BDD 50%, #8A53F0 100%);

/* 그림자 — 보라 글로우 */
--shadow-brand:        0 4px 16px rgba(124, 63, 230, 0.32);
--shadow-brand-strong: 0 6px 22px rgba(124, 63, 230, 0.45);

/* 텍스트 (그라데이션 면 위) */
--color-text-on-brand: #ffffff;

/* 기존 유지 */
--color-brand-primary:   var(--pink-500);   /* 단색 소형 UI용 */
--color-brand-disabled:  var(--ink-3);
--color-brand-bg-subtle: rgba(180,79,203,0.14);
```

### 적용 대상

| 컴포넌트 | 변경 전 | 변경 후 |
|---|---|---|
| 분석하기 버튼 (`.submit-btn`) | `--color-brand-primary` 단색 | `--color-brand-gradient` |
| 활성 칩 (`.chip.active`) | `--color-brand-primary` 단색 | `--color-brand-gradient` |
| 배우자직장 추가 버튼 (`.btn-add-wp2`) | 아웃라인 스타일 | `--color-brand-gradient` 채움 |
| 다크 그림자 | `rgba(168,46,27,*)` 벽돌빨강 | `rgba(124,63,230,*)` 보라 글로우 |
| on-brand 텍스트 | `white` 하드코딩 | `--color-text-on-brand` 토큰 |

### 주의 사항
- `background: gradient`는 `color` 상속 안 됨 → 텍스트는 반드시 `--color-text-on-brand` 별도 지정
- `filter: brightness()` hover 방식은 그라데이션과 충돌 → hover는 별도 lighter 그라데이션 토큰 사용
- 소형 UI(인라인 뱃지, 아이콘 버블 등)는 `--color-brand-primary` 단색 유지 — 그라데이션은 면적이 충분한 CTA에만

## 4. 완료 조건 (Acceptance Criteria)

- [x] 분석하기 버튼이 핑크-퍼플 그라데이션으로 표시됨
- [x] hover 시 밝은 그라데이션 + 보라 글로우 그림자
- [x] 통근시간 칩 선택(active) 시 동일 그라데이션 적용
- [x] 다크 모드에서 벽돌빨강 그림자 잔재 없음
- [x] `--color-text-on-brand` 토큰으로 하드코딩된 `white` 대체
- [ ] 로컬(SQLite) + Vercel(Supabase) 양쪽 동작 — 정적 CSS 변경이므로 별도 확인 불필요
