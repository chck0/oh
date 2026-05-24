# Spec: 추천 엔진 (통근버킷 × 평형 매트릭스)

> **상태**: Implemented  
> **구현 파일**: `app/ai.py` — `build_recommendations()`, `build_stats()`  
> **작성일**: 2026-05-24 (retrospective)

---

## 1. Why

MANIFESTO — "비교가 판단을 만든다. '이 집이 좋다'는 말은 의미 없다. '같은 통근시간 내에서 이 집이 가장 싸다'는 말은 유용하다."  
통근시간과 평형은 독립 축이다. 두 축의 교차 슬롯에서 최저가 1개만 추천하면 비교 기준이 명확해진다 (Why Tree #2).

---

## 2. User Story

```
As a result.html (카드 소비자),
I want to 카드 목록에 is_recommended·bucket_label·pick_reason이 부여되어 있으면,
so that 통근버킷별·평형별 최저가 추천 카드를 강조 표시할 수 있다.
```

---

## 3. Scope

### In-scope
- 통근시간 버킷 분류 (0~30분, 30~40분, 40~50분, 50~max분)
- (버킷 × 평형) 슬롯에서 최저가 1개 추천
- 같은 단지(apt_seq) 중복 추천 제거 (첫 슬롯에만 추천)
- `pick_reason` 한 줄 생성 (슬롯 내 최저가 + 평형 최단버킷 대비 차액)
- 통계 계산 (통근-가격 곡선, 평형별 평균, 연식 분포)

### Out-of-scope
- LLM 기반 순위 조정
- 사용자 선호 학습 / 피드백 반영
- 학군·환경 가중치

---

## 4. Functional Requirements

### 버킷 정의 (`make_buckets`)
- 0~30분 (고정)
- 30분~max_minutes: 10분 단위 슬라이스
- 예: max=60 → [(0,30), (30,40), (40,50), (50,60)]

### 추천 선정 (`build_recommendations`)
- F1. 각 카드에 `bucket_idx`, `bucket_label` 부여
- F2. 슬롯 = (bucket_idx, pyeong_type) 단위로 그룹화
- F3. 평형별 최단버킷 최저가 = `baseline_by_pt` (차액 계산 기준)
- F4. 버킷 오름차순 × 평형 순으로 슬롯 순회
- F5. 슬롯 내 price_low 오름차순 정렬 → apt_seq 미중복 1개 추천
- F6. 추천 카드에 `is_recommended=True`, `price_diff_vs_fastest`, `pick_reason` 부여
- F7. 나머지 카드 `is_recommended=False`

### 통계 (`build_stats`)
- F8. total, avg_price (전체 카드 기준)
- F9. commute_curve: 버킷별 평균가 + 매물 수
- F10. pyeong_breakdown: 평형별 평균가 + 매물 수
- F11. age_breakdown: 신축(10년↓) / 준신축(20년↓) / 구축 / 미상

---

## 5. Non-functional Requirements

- **성능**: 카드 수백 개 처리 < 50ms (순수 Python 로직)
- **결정론**: 동일 입력 → 동일 추천 (정렬 기준 고정)

---

## 6. UX / Vibe

추천 카드는 result.html에서 "추천" 배지 + 강조 스타일로 표시.  
`pick_reason`은 카드 하단에 작게 표시 ("30~40분 · 30평대 중 최저가. 최단권보다 3천만 저렴").

---

## 7. Data Model

**카드 입력 (dict)**

| 필드 | 타입 | 설명 |
|---|---|---|
| apt_seq | str | 단지 고유 ID |
| pyeong_type | str | 평형 분류 |
| total_time_min | int | ODsay 대중교통 시간 |
| price_low | int (만원) | 기간 내 최저 실거래가 |

**카드 출력 (추가 필드)**

| 필드 | 타입 | 설명 |
|---|---|---|
| bucket_idx | int | 버킷 인덱스 |
| bucket_label | str | "30분 이내" / "30~40분" 등 |
| is_recommended | bool | 추천 여부 |
| price_diff_vs_fastest | int (만원) | 같은 평형 최단버킷 대비 차액 |
| pick_reason | str | 추천 사유 한 줄 |

---

## 8. API / Interface

```python
# 진입점
result = build_recommendations(cards: list[dict], max_minutes: int) -> dict
# result['buckets']: 버킷 목록
# result['cards']:   카드 목록 (필드 추가됨)

stats = build_stats(cards: list[dict], buckets: list[dict]) -> dict
```

---

## 9. Edge Cases

| 케이스 | 현재 동작 |
|---|---|
| 카드 없음 | `{'buckets': [], 'cards': []}` |
| 특정 슬롯 카드 없음 | 해당 슬롯 추천 없음 (빈 슬롯) |
| 같은 단지가 여러 슬롯 해당 | 첫 번째 슬롯에만 추천, 나머지 is_recommended=False |
| 연식 정보 없음 | age_breakdown.unknown 카운트 |

---

## 10. Acceptance Criteria

- [x] 각 (버킷, 평형) 슬롯에서 최저가 1개가 is_recommended=True
- [x] 같은 apt_seq는 하나의 슬롯에서만 추천
- [x] pick_reason에 슬롯명과 차액 포함
- [x] build_stats 버킷별 commute_curve 반환
- [x] 연식 분포 4구간 반환

---

## 11. 개선 아이디어 (Open)

- 추천 카드 상한 설정 (예: 최대 6장, 나머지 "더 보기")
- 평형 정렬 순서 사용자 지정
- 역 통근 방향 고려 (집 → 직장 경로 외 직장 → 집도 계산)
