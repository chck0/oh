# 부동산 검증 AI 에이전트 — 리포트 UI 기술 스택

> **프로젝트**: PropCheck AI — 부동산 검증 AI 에이전트 종합 리포트 화면  
> **버전**: v1.0  
> **작성일**: 2026-05-05  
> **대상 파일**: `index.html` (모바일), `index-web.html` (웹 데스크탑)

---

## 목차

1. [개요](#개요)
2. [아키텍처](#아키텍처)
3. [프론트엔드 기술 스택](#프론트엔드-기술-스택)
4. [UI 컴포넌트 구성](#ui-컴포넌트-구성)
5. [디자인 시스템](#디자인-시스템)
6. [지도 구현](#지도-구현)
7. [인터랙션 & 애니메이션](#인터랙션--애니메이션)
8. [반응형 전략](#반응형-전략)
9. [파일 구조](#파일-구조)
10. [외부 의존성](#외부-의존성)

---

## 개요

본 프로젝트는 부동산 AI 에이전트의 분석 결과를 사용자에게 전달하는 **종합 리포트 화면(UI 프로토타입)**입니다.  
별도의 빌드 도구나 프레임워크 없이 **Vanilla HTML/CSS/JavaScript** 단일 파일로 구성된 정적 페이지이며, CDN을 통해 외부 라이브러리를 로드합니다.

### 핵심 설계 원칙

| 원칙 | 설명 |
|------|------|
| **Zero-build** | Webpack, Vite 등 번들러 없이 브라우저에서 직접 실행 |
| **Single-file** | 모든 CSS·JS·HTML이 하나의 파일에 인라인 |
| **CDN-only 의존성** | 외부 패키지는 CDN URL로만 로드 (npm 불필요) |
| **Mobile-first** | 390px 기준으로 설계 후 데스크탑으로 확장 |

---

## 아키텍처

```
┌──────────────────────────────────────────┐
│             Static HTML Page             │
│                                          │
│  ┌─────────────┐   ┌──────────────────┐  │
│  │  index.html  │   │ index-web.html   │  │
│  │  (Mobile)    │   │  (Desktop Web)   │  │
│  │  390px       │   │  1180px          │  │
│  └──────┬───────┘   └────────┬─────────┘  │
│         │                   │            │
│         └────────┬──────────┘            │
│                  ▼                        │
│    ┌─────────────────────────────┐        │
│    │     Shared Design System    │        │
│    │  CSS Custom Properties      │        │
│    │  (colors, radius, shadow)   │        │
│    └──────────────┬──────────────┘        │
│                   │                       │
│    ┌──────────────▼──────────────┐        │
│    │       External CDN Libs     │        │
│    │  • Pretendard (font)        │        │
│    │  • Leaflet.js (map)         │        │
│    │  • OpenStreetMap tiles      │        │
│    └─────────────────────────────┘        │
└──────────────────────────────────────────┘
```

---

## 프론트엔드 기술 스택

### 1. 마크업 — HTML5

```
HTML 버전   : HTML5
인코딩      : UTF-8
뷰포트      : width=device-width, initial-scale=1.0
```

- Semantic HTML 태그 사용 (`<nav>`, `<strong>`, `<button>`)
- SVG 인라인 (네비게이션 아이콘, 레이더 차트)
- 이모지(Unicode) 아이콘 활용으로 외부 아이콘 폰트 의존성 제거

---

### 2. 스타일링 — CSS3

#### CSS Custom Properties (Design Tokens)

모든 색상, 간격, 그림자를 `:root`의 CSS 변수로 중앙 관리합니다.

```css
:root {
  /* Colors */
  --navy: #0F1B35;
  --blue: #1E5EFF;
  --green: #00B85E;
  --orange: #FF6B35;
  --red: #E53935;
  --yellow: #F5A623;

  /* Surfaces */
  --bg: #F4F6FA;
  --surface: #FFFFFF;
  --border: #E8ECF4;

  /* Typography */
  --text-primary: #0F1B35;
  --text-secondary: #5A6476;
  --text-muted: #9AA2B4;

  /* Shape */
  --radius-sm: 10px;
  --radius-md: 16px;
  --radius-lg: 24px;

  /* Elevation */
  --shadow-sm: 0 1px 4px rgba(15,27,53,0.06);
  --shadow-md: 0 4px 16px rgba(15,27,53,0.10);
  --shadow-lg: 0 8px 32px rgba(15,27,53,0.14);
}
```

#### 사용 기술

| 기술 | 용도 |
|------|------|
| **CSS Grid** | 데스크탑 5열 점수 카드, 지도+사이드바 2열 레이아웃 |
| **CSS Flexbox** | 헤더, 카드 내부 행 정렬, 버튼 그룹 |
| **CSS Transitions** | 점수 바 애니메이션, hover 효과, 카드 lift |
| **CSS `@keyframes`** | "NEW" 배지 shimmer 효과 |
| **`linear-gradient`** | 히어로 배경, 점수 바 색상 |
| **`radial-gradient`** | 히어로 배경 광원 효과, 레이더 차트 채움 |
| **CSS `::before` / `::after`** | 카드 왼쪽 컬러 바, 인사이트 카드 배경 이모지 |
| **`position: sticky`** | 데스크탑 상단 Nav Bar 고정 |
| **`overflow: hidden`** | 카드 내 요소 클리핑 |
| **`backdrop-filter`** | (지원 시) 반투명 레이어 |
| **`scrollbar-width: none`** | 범례 가로 스크롤 바 숨김 |

---

### 3. 인터랙션 — Vanilla JavaScript (ES6+)

빌드 없이 `<script>` 태그 내 순수 JS로 구현합니다.

#### 주요 기능

```javascript
// 1. 점수 바 진입 애니메이션
window.addEventListener('load', () => {
  const fills = document.querySelectorAll('.cat-bar-fill, .vote-bar-fill');
  fills.forEach(el => {
    const target = el.style.width;
    el.style.width = '0';
    requestAnimationFrame(() => setTimeout(() => el.style.width = target, 120));
  });
});

// 2. 지도 레이어 토글 (전체 / 교통 / 학교)
function toggleLayer(mode, btn) { ... }

// 3. 범례 클릭 → 지도 flyTo 애니메이션
function flyTo(key) {
  map.flyTo(LOCATIONS[key].latlng, 17, { duration: 0.8 });
  setTimeout(() => LOCATIONS[key].marker.openPopup(), 850);
}
```

#### 사용 ES6+ 문법

| 문법 | 사용처 |
|------|--------|
| `const` / `let` | 모든 변수 선언 |
| Arrow function | 콜백, 이벤트 핸들러 |
| Template literals | DOM 마커 HTML 생성 |
| `Object.entries()` | LOCATIONS 순회 |
| `Set` | 레이어 필터링 집합 연산 |
| `requestAnimationFrame` | 애니메이션 시작 타이밍 |
| Destructuring | 마커 설정 configs 배열 |

---

## UI 컴포넌트 구성

### 모바일 (`index.html`) — 컴포넌트 목록

```
📱 phone-frame (390px)
├── status-bar          상태바 (시간, 배터리)
├── nav-bar             뒤로가기 + 제목 + 공유
├── hero                매물명 + 총점 + 별점 + verdict
├── verdict-banner      경고 배너 (신중 검토 권고)
├── map-card            ── 지도 섹션 ──
│   ├── map-header      타이틀 + 레이어 토글 버튼
│   ├── #map            Leaflet 지도 (220px)
│   ├── map-info-strip  교통 요약 정보
│   └── map-legend      5개 장소 범례 (클릭 flyTo)
├── vote-card           에이전트 투표 (바 + 칩)
├── radar-wrap          5각형 레이더 차트 (SVG)
├── categories          영역별 5개 점수 카드
├── insight-card        핵심 쟁점 (Pro/Con)
├── actions             액션 버튼 (메인 1 + 보조 2)
├── disclaimer          면책 고지
└── bottom-nav          하단 탭바
```

### 데스크탑 (`index-web.html`) — 레이아웃 구조

```
🖥️ Full-width (max 1180px)
├── topnav (sticky)         로고 + 브레드크럼 + 액션버튼
└── page (.page)
    ├── hero-strip           2단 (좌: 매물정보 / 우: 점수)
    ├── grid-scores          5열 점수 카드 (CSS Grid)
    ├── grid-map-insight     2열
    │   ├── 좌: map-card     Leaflet 지도 (320px)
    │   └── 우: 사이드바
    │       ├── vote card   에이전트 투표
    │       └── radar card  레이더 차트
    ├── insight-card         2열 Pro/Con 그리드
    ├── actions-row          3열 액션 버튼
    └── disclaimer           면책 고지
```

---

## 디자인 시스템

### 컬러 팔레트

| 역할 | 변수명 | Hex | 사용처 |
|------|--------|-----|--------|
| Primary | `--navy` | `#0F1B35` | 히어로 배경, 상단 Nav |
| Brand | `--blue` | `#1E5EFF` | CTA 버튼, 포인트 색상 |
| Success | `--green` | `#00B85E` | 입지(5점), 긍정 투표 |
| Warning | `--orange` | `#FF6B35` | 재무(2점), 신중 배지 |
| Danger | `--red` | `#E53935` | 리스크(2점), 경고 |
| Accent | `--yellow` | `#F5A623` | 시세(4점), 별점 |
| Background | `--bg` | `#F4F6FA` | 페이지 배경 |
| Surface | `--surface` | `#FFFFFF` | 카드 배경 |

### 타이포그래피

```
폰트패밀리: Pretendard (CDN)
폴백:       -apple-system, sans-serif

계층 구조:
  Hero 점수    900 weight  56~72px
  섹션 제목    700 weight  15~20px
  카드 제목    700 weight  14~15px
  본문         400 weight  13~14px
  레이블       700 weight  11px (대문자 + letter-spacing)
  캡션         400 weight  11~12px
```

**Pretendard** 선택 이유: 한국어 웹 환경에서 가독성이 가장 뛰어난 오픈소스 폰트. Apple San Francisco / Google Noto와 달리 웹폰트 최적화가 잘 되어 있으며 Variable 폰트 지원.

### 간격 시스템

```
카드 패딩:    16~22px
섹션 간격:    20px
카드 간격:    10~14px (모바일) / 14~20px (데스크탑)
페이지 여백:  20px (모바일) / 32px (데스크탑)
```

### 그림자 (Elevation)

```css
--shadow-sm: 0 1px 4px rgba(15,27,53,0.06);   /* 카드 기본 */
--shadow-md: 0 4px 16px rgba(15,27,53,0.10);  /* hover 상태 */
--shadow-lg: 0 8px 32px rgba(15,27,53,0.14);  /* 히어로 */
```

---

## 지도 구현

### 라이브러리: Leaflet.js v1.9.4

```html
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
```

**선택 이유**:
- 오픈소스 (BSD 2-Clause) — API 키 불필요
- 경량 (~42KB gzip) — 모바일에서도 빠름
- 풍부한 커스터마이징 API (커스텀 마커, 팝업, 레이어 제어)

### 타일 서버: CartoDB Light

```javascript
L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png')
```

**선택 이유**:
- 무료 (유량 제한 있음, 프로토타입에 적합)
- Light 테마 — UI 컬러 시스템(연한 배경)과 조화
- OpenStreetMap 기반 — 한국 지도 데이터 충실

### 커스텀 마커

Leaflet `DivIcon`을 사용해 CSS+이모지 조합의 커스텀 핀을 구현합니다:

```javascript
function makeIcon(color, emoji, size) {
  return L.divIcon({
    html: `<div style="
      background: ${color};
      border-radius: 50% 50% 50% 0;
      transform: rotate(-45deg);   /* 물방울 핀 모양 */
      border: 2.5px solid #fff;
      box-shadow: 0 3px 10px rgba(0,0,0,0.25);
    ">
      <span style="transform: rotate(45deg)">${emoji}</span>
    </div>`
  });
}
```

### 지도 기능 목록

| 기능 | 구현 방법 |
|------|-----------|
| 반경 시각화 | `L.circle()` — 점선 400m 원 |
| 레이어 토글 | `LayerGroup.addLayer / removeLayer` |
| 팝업 | `marker.bindPopup()` + 커스텀 HTML |
| flyTo 이동 | `map.flyTo(latlng, zoom, {duration})` |
| 줌 컨트롤 | `L.control.zoom()` (우측 하단 배치) |
| Attribution 제거 | `attributionControl: false` |

---

## 인터랙션 & 애니메이션

### 점수 바 진입 애니메이션

```
트리거: window load 이벤트
방식:  width 0 → 목표값, CSS transition
타이밍 함수: cubic-bezier(0.16, 1, 0.3, 1)  ← ease-out-expo 느낌
지연: 120ms (페이지 렌더 완료 후 시작)
```

### 카드 Hover 효과

```css
.score-card:hover {
  transform: translateY(-2px);    /* 2px 위로 lift */
  box-shadow: var(--shadow-md);   /* 그림자 강화 */
  transition: 0.15s;
}
```

### 지도 flyTo

```javascript
map.flyTo(latlng, 17, { duration: 0.8 });  // 0.8초 부드러운 이동
setTimeout(() => marker.openPopup(), 850); // 이동 완료 후 팝업
```

### NEW 배지 Shimmer

```css
@keyframes shimmer {
  from { opacity: 0.35; }
  to   { opacity: 0.85; }
}
/* 1.4초 주기 alternate 반복 */
```

---

## 반응형 전략

### Mobile (`index.html`)

- **고정 너비**: `max-width: 390px`, `margin: 0 auto`
- Phone Frame 컨셉 — 실제 앱처럼 보이도록 Status Bar 포함
- 모든 레이아웃: Flexbox 세로 스택

### Desktop (`index-web.html`)

- **최대 너비**: `max-width: 1180px`, `margin: 0 auto`
- CSS Grid 다중 열 레이아웃 (2열, 3열, 5열)
- Sticky 상단 Nav Bar (60px 고정)
- `@media (max-width: 900px)` 에서 1열로 collapse

```css
@media (max-width: 900px) {
  .grid-2col, .grid-3col,
  .grid-scores, .grid-map-insight,
  .actions-row {
    grid-template-columns: 1fr;  /* 모두 1열로 */
  }
}
```

---

## 파일 구조

```
realestate-report/
├── index.html          📱 모바일 버전 (단일 파일, ~600줄)
├── index-web.html      🖥️ 데스크탑 웹 버전 (단일 파일, ~700줄)
└── TECH_STACK.md       📄 이 문서
```

### 파일 구성 (각 HTML)

```
index.html
├── <head>
│   ├── Leaflet CSS (CDN)
│   ├── Leaflet JS (CDN)
│   └── <style> 인라인 CSS (~350줄)
│       ├── CSS Custom Properties
│       ├── Layout (phone-frame, sections)
│       ├── Components (card, bar, badge, map...)
│       └── Animations (@keyframes)
├── <body>
│   ├── HTML 마크업 (~180줄)
│   └── <script> 인라인 JS (~100줄)
│       ├── Leaflet 지도 초기화
│       ├── 커스텀 마커 생성
│       ├── 레이어 토글 함수
│       ├── flyTo 함수
│       └── 바 애니메이션 초기화
└── 총 ~600줄
```

---

## 외부 의존성

| 라이브러리 | 버전 | 용도 | 라이선스 | 로드 방식 |
|-----------|------|------|----------|-----------|
| **Pretendard** | latest | 한국어 웹폰트 | OFL-1.1 | CSS `@import` (JSDelivr CDN) |
| **Leaflet.js** | 1.9.4 | 인터랙티브 지도 | BSD-2-Clause | `unpkg` CDN |
| **CartoDB Basemaps** | - | 지도 타일 | ODC-ODbL | Leaflet TileLayer |
| **OpenStreetMap** | - | 지도 데이터 원본 | ODC-ODbL | (CartoDB 경유) |

### CDN URL 목록

```
폰트:
https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css

Leaflet CSS:
https://unpkg.com/leaflet@1.9.4/dist/leaflet.css

Leaflet JS:
https://unpkg.com/leaflet@1.9.4/dist/leaflet.js

지도 타일:
https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png
```

> **⚠️ 프로덕션 배포 시 주의사항**
> - CartoDB 타일은 하루 75만 요청 무료 제한 → 트래픽 증가 시 유료 플랜 또는 자체 타일 서버 고려
> - CDN URL은 인터넷 연결 필요 → 오프라인 환경이면 로컬 번들 필요
> - 실제 주소 데이터(광명역 좌표 등)는 Mock 데이터이며 실제 API 연동 필요

---

## 향후 기술 확장 방향

| 항목 | 현재 | 권장 확장 |
|------|------|-----------|
| 프레임워크 | Vanilla JS | React / Next.js (컴포넌트 재사용) |
| 스타일링 | Inline CSS | Tailwind CSS + CSS Modules |
| 지도 실주소 | Mock 좌표 | 카카오맵 API / 네이버 지도 API |
| 데이터 | 하드코딩 | REST API 연동 (AI 분석 결과 JSON) |
| 폰트 서빙 | CDN | Self-hosted (GDPR, 속도 최적화) |
| 번들링 | 없음 | Vite (빠른 빌드, HMR) |
| 타입 | JavaScript | TypeScript |
| 테스트 | 없음 | Playwright (E2E), Vitest (unit) |

---

*PropCheck AI — 부동산 검증 AI 에이전트 | 대학원 조별 프로젝트 | 2026년 5월*
