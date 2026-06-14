# 바둑이 컴포넌트 가이드

> 부동산 추천 서비스 "바둑이"의 핵심 컴포넌트 라이브러리.
> 컬러(`DESIGN_SYSTEM.md`) + 타이포(`TYPOGRAPHY.md`) 위에 구축.

**버전**: 0.3
**최종 수정**: 2026-06-14
**관련 파일**: `components.css`

---

## 1. 컴포넌트 선정 원칙

이 문서는 **부동산 추천 서비스에 꼭 필요한 컴포넌트**만 다룹니다. 일반적인 디자인 시스템(버튼만 7종, 인풋만 10종 식)이 아니라, 바둑이 서비스의 실제 사용 흐름에 등장하는 컴포넌트 위주로 정리합니다.

### 사용자 흐름과 컴포넌트 매핑

| 흐름 | 필요 컴포넌트 | 섹션 |
|------|-------------|------|
| 직장 주소 입력 | 검색바, 텍스트 인풋 | §3 |
| 조건 설정 | 필터 칩, 슬라이더, 셀렉트 | §3, §4 |
| 지도 탐색 | 지도 핀, 클러스터 | §6 |
| 매물 보기 | 매물 카드, 상태 태그 | §5, §4 |
| 비교/저장 | 체크박스, 토글, 메트릭 패널 | §7, §8 |
| 액션 실행 | 버튼 (Primary/Secondary/Ghost) | §2 |

---

## 2. 버튼 (Button)

### 2.1. Variants — 4종

| 종류 | 용도 | 시각적 특징 |
|------|------|------------|
| **Primary** | 메인 액션 (자세히 보기, 검색, 제출) | 빨강 배경 + 흰 텍스트 |
| **Secondary** | 보조 액션 (저장, 취소, 뒤로) | 흰 배경 + 회색 테두리 |
| **Ghost** | 부수적 액션 (필터 해제, 더보기) | 배경/테두리 없음 |
| **Link** | 인라인 텍스트 액션 | 밑줄 + 빨강 텍스트 |

**규칙**: 한 화면에 Primary 버튼은 1개만. 두 개 이상이면 위계가 깨집니다.

### 2.2. Sizes — 3단계

| 크기 | 높이 | padding | font-size | 용도 |
|------|------|---------|-----------|------|
| Small | 28px | 6px 12px | 12px | 칩 옆 액션, 카드 내부 |
| Medium (기본) | 38px | 10px 18px | 14px | 일반 상황 |
| Large | 48px | 13px 24px | 15px | 메인 CTA, 모바일 |

### 2.3. States — 4단계

- **Default**: `--color-brand-primary` (#A82E1B)
- **Hover**: `--color-brand-hover` (#7E2113) — 마우스 올림
- **Active**: `--color-brand-active` (#4D140C) — 누르는 중
- **Disabled**: `--color-brand-disabled` (#E89789) — `cursor: not-allowed`

### 2.4. 아이콘 버튼
- 텍스트 + 아이콘: 아이콘 16px, 텍스트 왼쪽
- 아이콘만: 38x38px 정사각형, 반드시 `aria-label` 필수

### 2.5. 사용 예시
```html
<!-- Primary CTA -->
<button class="btn btn-primary btn-md">자세히 보기</button>

<!-- 아이콘 포함 -->
<button class="btn btn-primary btn-md">
  <i class="ti ti-search"></i>매물 검색
</button>

<!-- 아이콘만 (반드시 aria-label) -->
<button class="btn btn-secondary btn-icon" aria-label="저장">
  <i class="ti ti-heart"></i>
</button>
```

---

## 3. 입력 (Input)

### 3.1. Text Input

기본 텍스트 입력. 라벨은 위에 배치 (placeholder 없이 라벨로만 표시되는 패턴은 금지).

- 높이: 40px
- padding: 10px 14px
- border: 1px solid `--color-border-strong` (#C9C5BF)
- 포커스 시: 1.5px solid `--color-brand-primary`, outline 없음
- border-radius: 8px

### 3.2. Search Bar (지도 위 오버레이)

지도 위에 떠있는 검색바. 일반 인풋과 다르게 둥글고 그림자가 있음.

- pill shape (border-radius: 24px)
- `--shadow-md` 적용
- 왼쪽: 검색 아이콘
- 오른쪽: 필터 진입 버튼 (구분선으로 분리)

### 3.3. Range Slider (가격·통근시간 범위)

부동산은 **단일 값이 아니라 범위 선택이 핵심**입니다. 양쪽 핸들 두 개를 가진 듀얼 슬라이더 필수.

- 트랙 높이: 4px
- 트랙 배경: `--color-border-strong` (#C9C5BF)
- 활성 구간(fill): `--color-brand-primary`
- 핸들: 22x22px, 흰 배경 + 빨강 테두리 3px + `--shadow-md`
- 값 표시: 상단 레이블 배지 ("최소 제한없음 / 최대 5억"), tabular nums 적용
- 눈금(tick): 하단에 0원 / 5억 / 10억 / 15억 / 20억+ 표시
- 범위: 0 ~ 20억, step: 5000만원 단위
- 두 핸들 교차 방지: 최소 간격 5000만원 유지

**구현 파일**: `web/search.html` `.price-slider-wrap` / `onPriceSlider()` 함수

### 3.4. 자동완성 (Autocomplete)

직장 주소 입력 시 필수. 드롭다운으로 후보 표시.
- 최대 표시: 5개
- 선택된 항목: `--color-bg-subtle` 배경
- 키보드 ↑↓ 이동 가능

---

## 4. 칩 · 태그 · 배지

세 가지를 명확히 구분해서 씁니다. 헷갈리면 시스템 일관성이 깨집니다.

### 4.1. Filter Chip (선택 가능)
**클릭 가능한 필터**. 상태가 있음 (선택/미선택).

- pill shape, 높이 28px
- 선택됨: 빨강 배경 + 흰 텍스트 + X 아이콘
- 미선택: 흰 배경 + 회색 테두리 + 검은 텍스트
- font-size: 13px

### 4.2. Status Tag (정보 표시)
**상태나 정보를 보여주기만 함**. 클릭 불가.

- pill shape, 높이 22px
- 의미별 색상 (DESIGN_SYSTEM.md §3.3 참조):
  - 통근시간 → Info (파랑)
  - 시세 적정 → Success (초록)
  - 시세 높음 → Warning (앰버)
  - 베스트 매치 → Brand (빨강)
- font-size: 12px

### 4.3. Badge (강조 라벨)
**짧고 강한 라벨**. 카드 상단, 카운트, 상태 표시.

- 사각형 또는 pill
- font-size: 10~11px, weight: 600, letter-spacing: 1.5px
- 보통 영문 대문자 (BEST, NEW, HOT)
- 카운트 배지는 원형 (필터 옆 "3", 알림 옆 숫자)

---

## 5. 매물 카드 (Property Card)

부동산 서비스의 핵심 컴포넌트. 정보 위계가 가장 중요합니다.

### 5.1. 정보 위계 (Top to Bottom)

```
┌──────────────────────────────┐
│ [BEST MATCH 배지]    [♥ 저장] │  ← 메타 (선택사항)
│                              │
│ 매물 이름                    │  ← Heading (18px / 600)
│ 주소 (구·동)                 │  ← Caption (12px / 400)
│                              │
│ 5억 8,000만                  │  ← Price Large (24px / 700)
│                              │
│ [통근27분] [시세적정]        │  ← Status Tags
│                              │
│ ─────────────────────        │  ← Divider
│ 25평 · 12/15층 · 2018년      │  ← Metric Group
└──────────────────────────────┘
```

### 5.2. 스펙
- 배경: `--color-bg-panel` (#FFFFFF)
- 테두리: 1px solid `--color-border-default`
- border-radius: 12px (`--radius-lg`)
- 그림자: `--shadow-md` (기본), `--shadow-lg` (호버)
- 패딩: 16px

### 5.3. Variants

| 종류 | 차이점 |
|------|--------|
| **Recommended** | 좌측 빨강 액센트 라인(4px), 슬롯칩+단지명+가격+메타 3줄 구조. AI 한마디 기본 접힘(토글 클릭 시 펼침) |
| **List (일반)** | 왼쪽: 단지명+메타 / 오른쪽: 가격+통근시간 한 줄 flex row. 코멘트 없음 |
| **Selected** | 빨강 테두리 1.5px |

**추천 카드 정보 위계 (2026-06-14 개편)**:
```
[슬롯칩: 30~40분 | 20평대]          ← 통근버킷×평형 (11px, 브랜드색)
단지명                  5억           ← 단지명(16px/700) + 가격(18px/700)
동 · 세대수 · 최고층               ← 메타 (12px, gray)
[통근N분] [이유칩] [이유칩]          ← 이유 칩 3개
▼ AI 한마디 (클릭 시 펼침)          ← 기본 접힘
```

**일반 카드 구조**:
```
단지명 평형        [가격]
동 · 세대수        [통근N분]
```

### 5.4. 호버 인터랙션
- 그림자 강해짐 (`--shadow-md` → `--shadow-lg`)
- 200ms transition
- transform 등 큰 움직임 금지 (지도 위 카드라 흔들리면 어지러움)

---

## 6. 지도 핀 (Map Pin)

`DESIGN_SYSTEM.md §4`에 정의된 5종 핀의 상세 스펙.

### 6.1. 공통 스펙
- pill shape (border-radius: 13~15px)
- font-feature-settings: 'tnum' 필수
- 핀 아래 화살촉(꼬리)은 8x8px 마름모 회전 또는 SVG path

### 6.2. 종류별 스펙

| 종류 | 배경 | 텍스트 | 테두리 | 그림자 | 크기 |
|------|------|--------|--------|--------|------|
| **Recommended** | `--red-600` | 흰색 | 없음 | red glow (`--shadow-pin-recommended`) | 24px 높이 |
| **Default** | 흰색 | 검정 | `--gray-300` 1px | `--shadow-md` | 22px |
| **Visited** | `--gray-100` | `--gray-500` | `--gray-200` | 없음 | 22px |
| **Selected** | `--gray-900` | 흰색 | 빨강 outline 3px | `--shadow-lg` | 28px |
| **Cluster** | 흰색 (원형) | 빨강 | 빨강 2px | `--shadow-lg` | 44x44px |

### 6.3. 핀 표기 규칙
- 줄임 표기: 소수 1자리까지 (`5.8억`, `12.3억`)
- 1억 미만: 만 단위 (`9,800만`)
- 클러스터: 매물 수만 (`128`)

### 6.4. 인터랙션
- 호버 시: 살짝 위로 (translateY(-2px)) + 그림자 강화
- 클릭 시: Selected 상태로 전환 + 상세 카드 표시
- 줌 레벨에 따라 일정 거리 이내 핀들은 자동으로 클러스터로 묶임

---

## 7. 선택 컨트롤 (Toggles)

### 7.1. Checkbox
- 크기: 20x20px
- border-radius: 4px
- 체크됨: `--color-brand-primary` 배경 + 흰 체크 아이콘
- 미체크: 흰 배경 + `--color-border-strong` 1.5px

### 7.2. Radio
- 크기: 20x20px (원형)
- 선택됨: 빨강 외곽 + 빨강 내부 점 (10px)
- 미선택: 회색 외곽만

### 7.3. Switch (Toggle)
- 트랙: 36x20px, border-radius: 10px
- 핸들: 16x16px 흰 원
- 켜짐: 빨강 트랙
- 꺼짐: `--gray-300` 트랙

**사용 가이드**:
- Checkbox: 다중 선택 (필터 옵션)
- Radio: 단일 선택 (전세/월세/매매)
- Switch: 즉시 적용되는 설정 (알림 켜기, 다크모드)

---

## 8. 패널 (Panel)

지도 위에 떠있는 콘텐츠 박스의 통칭. 4종류가 있습니다.

### 8.1. Floating Panel (떠있는 패널)
필터, 검색 결과 미리보기 등. 지도 위 일시적으로 표시.

- 배경: 흰색
- 테두리: 1px solid `--color-border-default`
- border-radius: 12px
- 그림자: `--shadow-lg`
- 패딩: 16px
- 닫기 버튼 (X) 우상단 필수

### 8.2. Side Panel (사이드 패널)
좌측 또는 우측에 고정된 패널. 매물 리스트, 상세 정보.

- 높이: 100vh
- 너비: 380px (데스크톱), 100% (모바일)
- 헤더 + 스크롤 본문 구조
- 우측 그림자: `--shadow-lg`

### 8.3. Bottom Sheet (모바일)
모바일에서 상세 정보 표시. 위로 스와이프하면 전체 화면.

- 상단 핸들 바 (40x4px, gray-300, border-radius: 2px)
- border-radius: 16px 16px 0 0
- 그림자: `--shadow-xl` (위쪽으로)

### 8.4. Metric Group
가격·통근·매물수 등 메트릭 묶음 표시.

- 가로 배치, 구분선으로 분리
- 라벨(11px/400/gray-500) + 값(18px/600/gray-900 + 단위 12px/500/gray-700)
- 항상 tabular-nums 적용

---

## 9. 모달 & 다이얼로그

### 9.1. Modal
중앙 모달. 백드롭 어두움.

- 백드롭: rgba(26, 24, 22, 0.45)
- 모달 너비: max 480px
- 그림자: `--shadow-xl`
- ESC로 닫힘, 백드롭 클릭으로 닫힘

### 9.2. Toast (알림)
임시 알림 메시지. 우상단 또는 하단.

- 4종: success / info / warning / error
- 자동 사라짐: 4초 (단, 에러는 수동 닫기)
- 그림자: `--shadow-lg`

### 9.3. Confirm Dialog
중요한 액션 확인 (저장 취소, 삭제 등).

- 제목 (16px/600) + 본문 (14px/400) + 버튼 2개
- 파괴적 액션은 Primary 버튼이 회색 + 텍스트가 빨강

---

## 10. 접근성 체크리스트

모든 컴포넌트는 다음을 만족해야 합니다:

- ✅ 키보드만으로 모든 인터랙션 가능 (Tab, Enter, Space, Esc)
- ✅ 포커스 시각화 (포커스 링 또는 굵은 테두리)
- ✅ 색상만으로 정보 전달 금지 (아이콘/텍스트 병행)
- ✅ 텍스트와 배경 대비 4.5:1 이상 (큰 텍스트는 3:1)
- ✅ 아이콘 버튼은 `aria-label` 필수
- ✅ 모달 열림 시 포커스 트랩
- ✅ 폼 인풋은 `<label>` 연결 필수

---

## 11. 컴포넌트 우선순위 (구현 순서)

MVP에 꼭 필요한 순서로 정리:

### Phase 1 (MVP 필수)
1. Button (Primary, Secondary, Ghost + 사이즈 3종)
2. Text Input, Search Bar
3. Property Card (Default, Recommended)
4. Map Pin (5종)
5. Filter Chip, Status Tag
6. Range Slider (가격 + 통근시간)

### Phase 2 (확장)
7. Side Panel, Floating Panel
8. Checkbox, Radio, Switch
9. Metric Group
10. Modal, Toast

### Phase 3 (고도화)
11. Autocomplete (자동완성)
12. Bottom Sheet (모바일 최적화)
13. Image Gallery (매물 사진)
14. Confirm Dialog

---

## 12. 변경 이력

- **v0.1** (2026-05-16): 초안. 핵심 7개 컴포넌트 카테고리 정의, MVP 우선순위 설정.
