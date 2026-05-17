# 바둑이 모션 시스템

> 절제된 기능적 모션. 지도 위 UI를 안 흔들고 정보 비교를 방해하지 않음.
> Linear · Notion · 토스 노선. 화려함이 아니라 신뢰감 추구.

**버전**: 0.1
**최종 수정**: 2026-05-16
**관련 파일**: `motion.css`

---

## 1. 디자인 컨텍스트

### 바둑이 모션의 특수 제약

부동산 추천 서비스는 일반 SaaS·랜딩페이지와 모션 요구사항이 다릅니다.

1. **지도 위에서 동작** — 지도가 이미 움직이는 캔버스. UI까지 활발히 움직이면 멀미 유발.
2. **정보 비교가 핵심** — 카드들이 흔들리면 비교 불가. 정렬 안정성 우선.
3. **장시간 사용** — 매물 탐색은 30분+ 작업. 미세한 거슬림도 피로 누적.
4. **모바일 지도 인터랙션** — 핀치줌·드래그가 끊임없이. 추가 모션은 노이즈.

### 참고 노선
- **Linear** — 거의 모션 없음. fade·shadow만
- **Notion** — 즉각적, 깔끔, bounce 0
- **토스** — 절제된 트랜지션
- **Stripe** — 정적 + 미니멀 호버

### 안 따라갈 노선
- Apple 키노트형 화려한 페이지 전환
- 게이미피케이션 앱의 통통 튀는 모션
- 디즈니플러스/넷플릭스의 큰 카드 호버 줌

---

## 2. 5가지 원칙

### 2.1. 모션은 정보를 보조할 때만
"왜 이게 움직이는지" 한 문장으로 설명 가능해야 사용. 장식 모션 금지.

- ✅ 모달 등장: "사용자 주의를 끌어야 하므로 scale-in"
- ❌ 페이지 진입 시 카드 staggered fade: "예뻐서"

### 2.2. 지도 위 카드는 transform 금지
호버 시 살짝 떠오르는 효과 금지. **색상·그림자만** 변화.

이유: 지도가 드래그/줌으로 끊임없이 움직이는 중인데, UI까지 위치가 변하면 시각적 혼란. 토스·당근도 지도 영역에서 비슷한 절제 적용.

예외: **지도 핀**은 `translateY(-2px)` 호버 허용 (떠있다는 신호 필요).

### 2.3. Duration은 4단계만
80 / 120 / 200 / 300ms. 그 사이값(150·250·400·500 등) 금지. 분류 무너지면 시스템도 무너짐.

### 2.4. ease-out 기본, bounce 금지
- ✅ `cubic-bezier(0.16, 1, 0.3, 1)` (강한 ease-out)
- ✅ `cubic-bezier(0.65, 0, 0.35, 1)` (ease-in-out, 큰 움직임만)
- ✅ `linear` (반복 모션만)
- ❌ bounce, elastic, back, anticipate — 통통 튀는 효과는 부동산 톤과 안 맞음

### 2.5. prefers-reduced-motion 존중
OS에서 "동작 줄이기" 켜놓은 사용자는 **모든 모션 0.01ms로 축소**. 접근성 의무.

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

---

## 3. Duration 토큰

| 토큰 | 값 | 용도 |
|------|---|------|
| `--duration-instant` | 80ms | 클릭 피드백 (버튼 누름), 즉각 상태 전환 |
| `--duration-fast` | 120ms | 호버 (색 변화), 칩·태그 토글, 토글 스위치 |
| `--duration-normal` | 200ms | **기본값.** 그림자, 카드 호버, fade in, 일반 트랜지션 |
| `--duration-slow` | 300ms | 모달·패널 열림, 페이지 전환, 시트 슬라이드 |

**중간값 금지** — 150, 250, 400, 500ms 등은 사용하지 않음.

---

## 4. Easing 토큰

| 토큰 | 값 | 용도 |
|------|---|------|
| `--ease-out` | `cubic-bezier(0.16, 1, 0.3, 1)` | **기본값.** 빠르게 시작 → 부드럽게 멈춤 |
| `--ease-in-out` | `cubic-bezier(0.65, 0, 0.35, 1)` | 큰 움직임 (모달·패널). S자 곡선 |
| `--ease-linear` | `linear` | 반복 모션만 (스피너, shimmer) |

**금지 easing**:
- `ease-in` — 끝이 갑자기 멈춤. 부자연스러움
- `cubic-bezier(0.68, -0.55, 0.27, 1.55)` 류 bounce
- `cubic-bezier(0.34, 1.56, 0.64, 1)` 류 back

---

## 5. 인터랙션별 모션 규칙

### 5.1. 버튼
```css
.btn {
  transition: background var(--duration-fast) var(--ease-out),
              transform var(--duration-instant) var(--ease-out);
}
.btn:hover  { /* background 변화만 */ }
.btn:active { transform: scale(0.97); }
```

**규칙**: hover는 색만, active는 살짝 축소.

### 5.2. 매물 카드 (지도 위)
```css
.property-card {
  transition: box-shadow var(--duration-normal) var(--ease-out);
}
.property-card:hover {
  box-shadow: var(--shadow-lg);
  /* transform 절대 사용 금지 */
}
```

**규칙**: 그림자만 강해짐. 위치·크기 변화 금지. 200ms로 부드럽게.

### 5.3. 지도 핀 (예외 — transform 허용)
```css
.map-pin {
  transition: transform var(--duration-fast) var(--ease-out),
              box-shadow var(--duration-fast) var(--ease-out);
}
.map-pin:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-lg);
}
```

**규칙**: 핀은 "떠있다"는 신호가 필요하므로 -2px만 허용.

### 5.4. 필터 칩
```css
.chip {
  transition: background var(--duration-fast) var(--ease-out),
              border-color var(--duration-fast) var(--ease-out);
}
```

### 5.5. 토글 스위치
```css
.switch {
  transition: background var(--duration-fast) var(--ease-out);
}
.switch::after {
  transition: left var(--duration-fast) var(--ease-out);
}
```

### 5.6. 모달 등장
```css
@keyframes scale-in {
  from { opacity: 0; transform: scale(0.96); }
  to   { opacity: 1; transform: scale(1); }
}
.modal {
  animation: scale-in var(--duration-normal) var(--ease-out);
}
```

### 5.7. 사이드 패널 슬라이드
```css
@keyframes slide-right {
  from { opacity: 0; transform: translateX(-12px); }
  to   { opacity: 1; transform: translateX(0); }
}
.side-panel {
  animation: slide-right var(--duration-slow) var(--ease-in-out);
}
```

### 5.8. 토스트 알림
```css
@keyframes fade-up {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}
.toast {
  animation: fade-up var(--duration-normal) var(--ease-out);
}
```

---

## 6. 진입 애니메이션 (4가지만)

| 종류 | 효과 | 사용처 |
|------|------|--------|
| **fade-in** | opacity 0→1, 200ms | 토스트, 인라인 메시지 |
| **fade-up** | translateY(8px) + opacity, 250ms | 카드 리스트 등장 |
| **slide-right** | translateX(-12px) + opacity, 250ms | 사이드 패널, 드로어 |
| **scale-in** | scale(0.96→1) + opacity, 200ms | 모달, 팝오버 |

**금지**: staggered animation (여러 요소가 시차 두고 차례로 등장). 데모 단계의 가짜 화려함.

---

## 7. 로딩 상태

### 7.1. Skeleton (선호)
콘텐츠 영역(매물 카드, 리스트) 로딩 시 사용. 실제 레이아웃 보존하면서 shimmer.

```css
@keyframes shimmer {
  0%   { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
.skeleton {
  background: linear-gradient(90deg,
    var(--gray-100) 0%,
    var(--gray-50) 50%,
    var(--gray-100) 100%);
  background-size: 200% 100%;
  animation: shimmer 1.4s linear infinite;
}
```

### 7.2. Spinner (보조)
버튼 내부, 인라인 작은 로딩에만.

```css
@keyframes spin { to { transform: rotate(360deg); } }
.spinner {
  width: 16px; height: 16px;
  border: 2px solid var(--color-border-default);
  border-top-color: var(--color-brand-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
```

### 7.3. 풀스크린 로딩
**금지**. 화면 전체를 가리는 로딩은 사용자 인내력 시험. Skeleton으로 영역별 로딩.

---

## 8. 절대 금지 모션 목록

| 금지 모션 | 대신 |
|----------|------|
| Bounce / Elastic / Back easing | ease-out 또는 ease-in-out |
| 페이지 진입 시 staggered fade | 첫 로딩 skeleton만 |
| 패럴랙스 스크롤 | 정적 배경 |
| Hero 영역 자동재생 동영상 | 정적 이미지/지도 |
| 호버 시 카드 위로 떠오름 (지도 위) | 그림자 변화만 |
| 카드 클릭 시 전체 flip | 사이드 패널로 상세 열기 |
| 가격 숫자 카운트업 애니메이션 | 즉시 숫자 표시 |
| 페이지 전환 시 화면 전체 슬라이드 | 즉시 콘텐츠 교체 (또는 fade-up) |
| 마우스 따라가는 커스텀 커서 | OS 기본 커서 |
| 스크롤 시 요소 회전 | 정적 |

---

## 9. 의사 결정 체크리스트

새 모션 추가할 때 자문:

1. **이 모션이 정보 전달에 도움되나?** → 아니오 → 추가 안 함
2. **지도 위 요소인가?** → 예 → transform 금지, shadow만
3. **duration이 4단계 안에 있나?** → 아니오 → 분류 재검토
4. **easing이 ease-out·in-out·linear 중 하나인가?** → 아니오 → 사용 안 함
5. **prefers-reduced-motion 대응 되어 있나?** → 아니오 → 추가 필요

다섯 개 통과해야 사용.

---

## 10. 데모 단계의 가장 흔한 함정

> "조금만 더 화려하면 좋아 보일까?"

이 유혹이 모션 시스템을 무너뜨립니다. 부동산은 화려한 게 아니라 **믿음직한** 게 좋은 톤이에요.

**규칙**: 만들고 싶은 모션이 떠오르면, **그것의 1/3만 적용**. 그래도 충분히 보이고 거슬리지 않습니다.

예시:
- 떠오른 생각: "카드 호버 시 위로 5px + 그림자 강화 + 살짝 회전"
- 1/3 적용: "그림자만 강해짐 (200ms)"

---

## 11. 변경 이력

- **v0.1** (2026-05-16): 초안. 절제 노선, duration 4단계, easing 3가지, 금지 목록 명시.
