# BADUGI 디자인 핸드오프

> 새 Claude 세션에서 디자인 작업을 이어받기 위한 컨텍스트 문서.
> 이 파일 + 아래 명시한 파일들을 함께 첨부/공유하면 됨.

---

## 1. 프로젝트 개요

**서비스명**: BADUGI — 직장 주소 기반 아파트 추천 서비스
**컨셉**: "부동산 잘 아는 친구가 옆에서 추천해주는" 톤
**스택**: FastAPI + SQLite + Vanilla JS + Kakao Maps + Claude (Sonnet/Haiku)

**주요 흐름**:
1. `index.html` — 랜딩
2. `search.html` — 검색 조건 입력 (직장 주소, 최대 가격, 최대 통근시간, 평형대)
3. `result.html` — 결과 화면 (지도 + 카드 리스트)

---

## 2. 같이 첨부할 파일

### 디자인 시스템 (이미 정의됨)
- `web/static/design-system/DESIGN_SYSTEM.md` — 전체 가이드
- `web/static/design-system/COMPONENTS.md` — 컴포넌트 규칙
- `web/static/design-system/TYPOGRAPHY.md` — 타이포
- `web/static/design-system/MOTION.md` — 모션
- `web/static/design-system/tokens.css` — CSS 변수 (브랜드 컬러, 보더, spacing 등)
- `web/static/design-system/typography.css`
- `web/static/design-system/motion.css`

### 대상 페이지
- `web/result.html` — **이번 작업의 메인 타겟**
- `web/search.html`, `web/index.html` (보조)

---

## 3. 현재 result.html 구조

### 3-1. 데이터 흐름
1. `POST /api/search` — 조건 보내면 매물 카드 리스트 + 통계 + 버킷 정보 반환
2. 응답에 `llm_pending: true`면 백그라운드에서 AI 코멘트 생성 중
3. `GET /api/comments?wp_id=N&keys=apt:pt,apt:pt,...` 5초 간격 폴링으로 코멘트 받음
4. 카드 = `(apt_seq × pyeong_type)` 단위. 같은 단지의 다른 평형이면 카드 2장.

### 3-2. 화면 레이아웃 (현재)
```
┌── header ── (BADUGI, 처음으로, 조건 다시 입력)
├── summary-bar ── (직장주소 | 가격조건 | 시간조건 | 평형 | 총개수)
├── result-layout ──
│   ├── cards-panel (좌측 400px)
│   │   ├── stats-panel (3줄 인사이트)
│   │   │   - 총 N개 매물 · 평균 X억
│   │   │   - 통근×가격: 30분 이내 평균 ... → 40~50분 평균 ...
│   │   │   - 평형: 20평대 평균 ... · 30평대 평균 ...
│   │   │   - 연식: 신축 N · 준신축 N · 구축 N
│   │   ├── rec-section-head ("추천 N곳")
│   │   ├── rec-card × N (긴 카드, AI 코멘트 포함)
│   │   └── bucket-section × N (접힘, 클릭 시 펼침)
│   │       └── 평형별 list-card (짧음, 한 줄 코멘트)
│   └── map-panel (우측, 카카오맵)
│       - 단지 단위 핀 (같은 단지 다른 평형이면 핀 1개)
│       - 호버 → 툴팁 (평형 탭 전환)
│       - 핀 클릭 → 상세 패널 (cards-panel 자리에 표시)
└── pin-tooltip (fixed, 호버 시 표시)
```

### 3-3. 상호작용
- **카드 클릭** = 지도 pan만 (상세 안 열림)
- **지도 핀 클릭** = 상세 패널 열림 (cards-panel 자리)
- **호버** = 툴팁 미리보기
- **버킷 헤더 클릭** = 펼침/접힘

---

## 4. 디자인 작업 의뢰 요청사항

### 4-1. 톤 & 보이스 (이미 적용됨, 유지)
- 컬러 베이스: 빨강/주황 계열 (`--color-brand-primary: #A82E1B`)
- 한글 폰트: Pretendard
- **이모지 사용 금지** (앞서 다 제거함)
- 카드 모서리 둥글게, 미묘한 그림자

### 4-2. 작업 필요 부분 (디자이너에게 던질 거)

**다듬어줬으면 하는 영역**:

1. **추천 카드 (`.rec-card`)** — 시각적 위계 정리
   - 슬롯 라벨 (`30분 이내 · 20평대`), 단지명, 가격, 메타, 통근, 픽사유, AI 코멘트가 한 카드에 다 들어감
   - 정보 우선순위 시각화 필요

2. **통계 패널 (`.stats-panel`)** — 3줄짜리 데이터인데 가독성 부족
   - 통근-가격 곡선이 텍스트로만 표현됨 → 미니 시각화 검토 (작은 막대그래프 등)

3. **버킷 접힘 섹션 (`.bucket-section`)** — 너무 단조로움
   - 접힘 상태에서 그 버킷의 핵심 정보 (최저가, 매물수) 한눈에 보이게

4. **호버 툴팁 (`.pin-tooltip`)** — 평형 탭 전환 UX 다듬기
   - 탭 디자인이 너무 평범
   - 핀 클릭하면 상세로 가는 흐름 명시 (현재 작은 글씨로 안내)

5. **로딩 화면 (`.loading-overlay`)** — 영상 플레이리스트 + 진행 표시
   - 검색 끝나도 AI 분석은 백그라운드 진행 중 (사용자 모르게 빨리 끝내는 게 목표)
   - 사용자가 "결과 보기" 자연스럽게 누르도록 유도

6. **상세 패널** — 섹션 접힘 UX 정돈
   - 통근 경로 / 시세 분석 / 실거래 / 도보 시설 등 섹션이 많음
   - 정보가 너무 많을 때 단계적 노출 디자인

### 4-3. 디자인 시스템 준수
- 컬러는 `tokens.css` 변수 사용 (`var(--color-brand-primary)` 등)
- 새 컴포넌트 추가 시 `COMPONENTS.md` 패턴 따를 것
- 인라인 스타일 최소화 → 클래스로 추출

---

## 5. 최근 변경된 컨셉 요약

(직전 작업 세션에서 결정된 내용 — 디자인에 반영해야 함)

### 5-1. 추천 로직 (백엔드)
- **이전**: Pareto-optimal BEST / GOOD / SOSO / LAST 4단 등급
- **현재**: 통근버킷 (10분 단위) × 평형 매트릭스에서 각 슬롯별 최저가 1개를 추천. 같은 단지는 1번만 등장.
- 각 추천에 `pick_reason` (로직 생성), `friend_comment` (Sonnet 생성) 표시

### 5-2. AI 코멘트
- **추천 카드** = Sonnet, 2문장/80자 카톡 톤 (장점+단점)
- **일반 카드** = Haiku, 40자 한 줄
- 모든 카드에 코멘트 채워짐 (몰래 백그라운드 호출)

### 5-3. 상호작용 규칙
- 카드 클릭 → 지도 pan만
- 핀 클릭 → 상세 패널 직행
- 호버 → 툴팁 미리보기
- 클러스터링 X, 단지 단위 핀 (평형 2개 이상이면 호버 시 탭)

---

## 6. 새 Claude 세션 시작 시 권장 프롬프트

```
첨부한 HANDOFF_DESIGN.md를 먼저 읽고, 그 안의 "4. 디자인 작업 의뢰 요청사항"
섹션을 단계별로 진행해줘. 디자인 시스템 (tokens.css 등) 변수를 반드시 사용하고,
이모지는 절대 추가하지 마. 변경 전 result.html 현 상태를 먼저 읽어서 파악해.

우선순위: 1) 추천 카드 위계 정리 → 2) 통계 패널 가독성 → 3) 버킷 섹션 → 4) 툴팁

각 작업 끝마다 변경 사항 요약하고 다음 작업으로 넘어가기 전 확인 요청.
```

---

## 7. 첨부 파일 체크리스트

새 세션 시작할 때 첨부할 것:
- [ ] `HANDOFF_DESIGN.md` (이 파일)
- [ ] `web/result.html`
- [ ] `web/static/design-system/DESIGN_SYSTEM.md`
- [ ] `web/static/design-system/COMPONENTS.md`
- [ ] `web/static/design-system/TYPOGRAPHY.md`
- [ ] `web/static/design-system/tokens.css`
- [ ] (선택) `web/static/design-system/typography.css`, `motion.css`
