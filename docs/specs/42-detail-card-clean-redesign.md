# Spec 42: 상세 카드 정리 + 인스타 클린카드 리디자인 (Look A)

> 상태: Implemented(시안) | 작성일: 2026-06-16 | 브랜치: hjkang83
> 사용자 검토용 시안 — 마음에 안 들면 즉시 원복(단일 커밋).

## 1. Why (왜)

- **문제:** 단지 상세 카드 정보량이 과해 `whytree.md`의 Top Why("5분 안에 신뢰하고 결정 = 정보 과잉 차단")와 충돌. 특히 시세 KPI 3개(`단지 6개월`/`동평균 대비`/`동평균 차액`)가 같은 사실을 중복하고, 데이터 없는 KPI(`6개월 -`)가 빈칸으로 노출됨.
- **목표:** ① 정보 정리(중복 제거·결론 우선) + ② "인스타 감성" 클린 카드 비주얼(Look A). 브랜드(Baduki Red + Warm Gray) 토큰 위에 인스타식 레이아웃 문법(소프트 섀도 카드·여백·알약 칩·스탯 줄)을 입힘.

## 2. Scope (범위)

- **포함 (web/result.html, `renderDetailPanel`/`renderKPIHTML` + CSS):**
  - HERO를 "결론 우선" 클린카드로: 메타 → **스탯 줄(통근·최저가·세대)** → 친구 한마디.
  - **알약 칩**(평형·통근버킷).
  - 시세 KPI 3박스 → **한 줄 결론(verdict)** ("○○동 N평 평균보다 8,900만 비쌈 (+9.8%)"), 데이터 없으면 숨김.
  - 비주얼: 패널 배경 웜그레이 + 흰 카드(보더 제거 → 소프트 섀도 + 라운드 16px + 여백).
- **제외(안 함):**
  - 백엔드/API/DB 변경. 데이터 항목 자체 추가.
  - 섹션 구성(통근/시세/실거래/도보/건물) 자체는 유지 — 묶기(상세 근거 그룹)는 후속.
  - 지도/POI 로직.

## 3. 설계 (어떻게)

- **건드리는 파일:** `web/result.html` 뿐. **DB/API:** 없음.
- **스탯 줄:** `통근(total_time_min분) · 최저가(price_low→fmtPrice) · 세대(kaptdaCnt)`. 큰 숫자 + 작은 라벨.
- **칩:** `pyeong_type`(brand) + 통근버킷 라벨(cool). 근거 불명 항목은 안 만듦(whytree 신뢰).
- **verdict:** `renderKPIHTML(ps, umd_nm)` — vs_dong_diff/pct로 한 문장. change_6m_pct 있으면 보조줄. 없으면 '시세 비교 데이터 없음'.
- **CSS:** `.detail-panel__body` 배경 `--color-bg-subtle`, `.dp__hero`/`.dp__section` → 흰 카드(보더 제거, `border-radius:16px`, `box-shadow:0 2px 14px rgba(26,24,22,.05)`, margin). `.dp__header`(빨강 sticky)는 유지. 신규 `.dp-statrow/.dp-stat/.dp-chips/.dp-chip/.dp-verdict`.
- **기본 펼침:** 통근 경로·시세 분석 유지(verdict가 짧아져 높이 부담↓).

## 4. 완료 조건 (Acceptance Criteria)

- [x] AC1: HERO에 스탯 줄(통근·최저가·세대) + 알약 칩 노출.
- [x] AC2: 시세 KPI 3중복 → 한 줄 결론. 데이터 없는 KPI 미노출.
- [x] AC3: 패널이 웜그레이 배경 + 흰 소프트카드(보더 없음, 라운드, 여백)로 보임.
- [x] AC4: 브랜드 토큰(Baduki Red/Warm Gray) 유지, `.dp__header` 빨강 헤더 유지.
- [x] AC5: 단일 커밋 — 원복 용이.
- [x] 순수 프론트 — 백엔드/DB/API 무변경, 전체 테스트 통과.

## 5. Open Questions / 후속

- 룩 확정 시: 실거래·도보·건물을 "상세 근거" 한 묶음으로 그룹핑(②), 차트 on-tap 로딩(⑤).
