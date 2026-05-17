# 바둑이 디자인 시스템

> 부동산 추천 서비스 "바둑이"의 디자인 시스템.
> 컬러 · 타이포 · 컴포넌트 · 아이콘 · 모션의 단일 출처(single source of truth).

**버전**: 0.1 (2026-05-16)
**상태**: MVP 직전 — 부동산 추천 서비스에 필요한 모든 핵심 결정 완료

---

## 빠른 시작

### Claude에게 작업 시킬 때

이 폴더를 통째로 첨부하고 한 줄만 추가하세요:

```
이 폴더의 디자인 시스템대로 [원하는 것] 을 만들어줘.
```

Claude가 자동으로:
1. `README.md`에서 전체 맥락 파악
2. 필요한 가이드 문서 참조 (`COMPONENTS.md`, `TYPOGRAPHY.md` 등)
3. `*.css` 변수와 클래스를 사용한 일관된 코드 생성
4. 빨강 면적·아이콘 절제 등 제약 자동 준수

### 개발자가 코드에 적용할 때

`<head>`에서 한 번에 import:

```html
<!-- 외부 의존성: Pretendard + Tabler Icons -->
<link rel="stylesheet" as="style" crossorigin
  href="https://cdn.jsdelivr.net/gh/orioncactus/[email protected]/dist/web/static/pretendard.min.css" />
<link rel="stylesheet"
  href="https://cdn.jsdelivr.net/npm/@tabler/[email protected]/dist/tabler-icons.min.css" />

<!-- 디자인 시스템 (순서 중요) -->
<link rel="stylesheet" href="./baduki-design-system/tokens.css" />
<link rel="stylesheet" href="./baduki-design-system/typography.css" />
<link rel="stylesheet" href="./baduki-design-system/motion.css" />
<link rel="stylesheet" href="./baduki-design-system/icons.css" />
<link rel="stylesheet" href="./baduki-design-system/components.css" />
```

이후 컴포넌트에서:

```html
<button class="btn btn-primary btn-md">자세히 보기</button>

<article class="property-card">
  <h3 class="property-card__title">서초동 래미안</h3>
  <div class="property-card__price">
    <span class="property-card__price-num">5</span>
    <span class="property-card__price-unit">억</span>
    <span class="property-card__price-num" style="margin-left:4px;">8,000</span>
    <span class="property-card__price-unit">만</span>
  </div>
</article>
```

---

## 서비스 컨텍스트

**바둑이**는 사용자의 직장 주소를 기준으로 **통근시간 · 평형 · 가격**을 최적화해서 베스트 부동산 매물을 추천하는 서비스입니다.

- **메인 화면**: 지도 기반. 그 위에 UI 패널이 떠 있는 구조 (네이버부동산·호갱노노와 유사)
- **사용자 톤**: 친근하지만 절제됨 (당근·토스·오늘의집 노선, 사짜 부동산 아님)
- **정보 중심**: 가격·평수·통근시간 같은 숫자 비교가 핵심
- **사용 시간**: 30분 이상 장시간 탐색 → 눈에 편안해야 함

---

## 파일 구조

```
baduki-design-system/
├── README.md              ← 이 문서 (진입점)
│
├── 📄 가이드 문서 (Claude · 사람이 함께 읽음)
│   ├── DESIGN_SYSTEM.md   컬러 + 전체 디자인 원칙
│   ├── TYPOGRAPHY.md      Pretendard 타이포 + 숫자 표현 규칙
│   ├── COMPONENTS.md      12종 핵심 컴포넌트 명세
│   ├── ICONS.md           Tabler Icons 미니멀 사용 규칙
│   └── MOTION.md          절제된 모션 + 금지 목록
│
├── 🎨 토큰 (기계 판독)
│   └── tokens.json        W3C Design Tokens 표준 (Figma · Style Dictionary 호환)
│
└── 💻 코드 (개발 적용)
    ├── tokens.css         컬러 CSS 변수
    ├── typography.css     폰트 + 숫자 클래스
    ├── components.css     버튼 · 카드 · 인풋 등
    ├── icons.css          Tabler 헬퍼 클래스
    └── motion.css         duration · easing · keyframes
```

---

## 핵심 원칙 5가지

이 시스템 전체를 관통하는 결정들입니다. 모든 컴포넌트가 이 원칙에서 파생됩니다.

### 1. 흰색 베이스 + 지도 위 떠있는 UI
지도가 화면의 70%+를 차지하므로 모든 UI 패널은 **순백(#FFFFFF)** 배경. 크림·회색 베이스 금지.

### 2. 빨강은 액션·추천에만 (전체 면적 5% 이하)
시그니처 컬러 `#A82E1B`는 벽돌톤 빨강. 채도 낮춰 장시간 봐도 편안. 빨강이 정보가 되려면 희소해야 함.

### 3. 숫자가 정보의 핵심 — 폰트 위계로 처리
"5억 8,000만"에서 숫자는 Bold, 단위(억/만)는 Medium 한 단계 작게. `font-feature-settings: 'tnum'` 필수.

### 4. 아이콘은 미니멀 (전체 ~15개만)
매물 옵션(침실/욕실/주차)에 아이콘 절대 금지. 텍스트가 더 빠르게 읽힘. 화면당 6개 이하.

### 5. 모션은 절제 (지도 위는 그림자만)
Duration 4단계(80/120/200/300ms) + Easing 3가지(out/in-out/linear). Bounce 금지. 지도 위 카드는 transform 금지.

---

## 의존성

이 시스템은 두 개의 외부 라이브러리에 의존합니다.

| 라이브러리 | 용도 | 라이선스 | 크기 |
|----------|------|---------|------|
| [Pretendard](https://github.com/orioncactus/pretendard) v1.3.9 | 폰트 | SIL OFL (무료) | ~120KB (서브셋) |
| [Tabler Icons](https://tabler.io/icons) v3.0.0 | 아이콘 | MIT | ~1.7KB (웹폰트) |

둘 다 한국 서비스에서 사실상 표준이고, 상업적 사용 무료입니다.

---

## 어떤 문서부터 읽어야 하나

상황별 추천 경로:

### "처음 보는 사람"
1. `README.md` (이 문서) — 30초
2. `DESIGN_SYSTEM.md` — 2분, 핵심 원칙 파악
3. 만들 컴포넌트에 따라 해당 가이드만 선택적으로

### "버튼·카드 만드는 개발자"
1. `tokens.css` (변수 확인)
2. `COMPONENTS.md` §해당 컴포넌트
3. `components.css` (실제 코드)

### "가격·숫자 표시 만드는 개발자"
1. `TYPOGRAPHY.md` §4 (숫자·가격 표현)
2. `typography.css` (`.price` 클래스들)

### "지도 위 UI 만드는 개발자"
1. `DESIGN_SYSTEM.md` §4 (지도 핀 체계)
2. `COMPONENTS.md` §6 (Map Pin 5종 스펙)
3. `MOTION.md` §5 (지도 위 모션 제약)

### "디자이너 신규 합류"
모든 `*.md` 순서대로:
`DESIGN_SYSTEM → TYPOGRAPHY → COMPONENTS → ICONS → MOTION`

---

## 자주 묻는 결정 사항

### Q. 새 색을 추가하고 싶다
A. 먼저 `tokens.css`의 시맨틱 변수로 표현 가능한지 확인. 정말 없으면 `tokens.json`과 `tokens.css` 양쪽 모두 추가. 단순히 화면용 색 하나 더 만들지 말 것.

### Q. 어떤 아이콘 써야 할지 모르겠다
A. `ICONS.md` §5에 정의된 15개 안에서만 선택. 없으면 **텍스트로 대체 가능한지** 먼저 고려. 진짜 추가가 필요하면 `ICONS.md`에 등록 후 사용.

### Q. 호버 시 카드를 살짝 띄우고 싶다
A. 지도 위 카드면 금지. `MOTION.md` §5.2 참조. 그림자만 강하게(`--shadow-lg`).

### Q. 디자인 시안에 없던 컴포넌트가 필요하다
A. `COMPONENTS.md` §1의 사용자 흐름에 정말 필요한지 재확인. 필요하면 가이드에 새 섹션 추가 후 구현. 가이드 외 컴포넌트 임의 제작 금지.

### Q. Pretendard 말고 다른 폰트 쓰고 싶다
A. `TYPOGRAPHY.md` §1에 선택 근거 명시되어 있음. 변경하려면 시스템 전체 재검토 필요 (자간·줄높이 모두 영향).

---

## 변경 이력

### v0.1 (2026-05-16) — 초기 시스템 구축
- 컬러 시스템 (벽돌 빨강 + 따뜻한 회색)
- 타이포 시스템 (Pretendard, 9단계 스케일)
- 컴포넌트 (버튼·카드·인풋·핀 등 12종)
- 아이콘 가이드 (Tabler, 15개 한정)
- 모션 시스템 (절제 노선)

### 향후 추가 예정 (v0.2~)
- [ ] 실제 화면으로 시스템 검증
- [ ] Spacing & Layout 가이드 (그리드, 반응형)
- [ ] Form Patterns (직장 주소 입력, 회원가입 등)
- [ ] Dark Mode (v1.0 출시 후)

---

## 참고: 영감을 받은 시스템

이 디자인 시스템은 다음을 참고했습니다:

- **Linear** — 절제 노선, 모션 미니멀
- **Stripe** — 정보 중심, 신뢰감
- **토스** — 한국 사용자 톤, Pretendard
- **당근** — 친근한 입말, 채도 낮은 컬러
- **호갱노노** — 지도 위 UI 구조
- **Radix Colors** — 시맨틱 토큰 명명 규칙
- **W3C Design Tokens** — 토큰 포맷 표준

---

## 라이선스

이 디자인 시스템 문서는 바둑이 프로젝트 내부용입니다.
외부 라이브러리(Pretendard, Tabler Icons)는 각자의 라이선스를 따릅니다.
