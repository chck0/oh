# Spec 20: 다중 우선순위 정렬

> **상태**: 구현 완료 (AC1~AC12)
> **작성일**: 2026-05-28
> **업데이트**: 2026-06-09
> **구현 브랜치**: feat/multi-priority-sort

---

## 1. Why (왜 만드는가)

- 사용자마다 중요하게 보는 기준이 다름 — 어떤 사람은 통근시간이 1순위, 다른 사람은 가격이 1순위
- 현재는 추천 로직 순서로만 카드가 나열되어 있어 자기 기준으로 재정렬할 수 없음
- 1개 기준으로만 정렬하면 동점일 때 순서가 불명확 → 2·3순위로 타이브레이킹

---

## 2. Scope

### In-scope
- 검색 결과 상단에 1·2·3순위 드롭다운 정렬 UI
- 상위 순위에서 선택한 항목은 하위 순위 드롭다운에서 제거 (중복 방지)
- 클라이언트 사이드 정렬 (이미 받은 카드 배열을 JS에서 재정렬)
- `/api/search` 응답 카드에 신규 필드 추가 (서버 쿼리 확장)

### Out-of-scope
- 정렬 설정 localStorage 저장
- 오름차순/내림차순 토글 (모든 항목 기본값으로 고정 — 아래 표 참조)
- 모바일 전용 UI 최적화

---

## 3. 정렬 항목

| 항목명 | 필드 | 기본 방향 | 출처 | 구현 |
|---|---|---|---|---|
| 통근시간 | `total_time_min` | 오름차순 (짧을수록 위) | ODsay (기존) | ✅ |
| 최저 거래가 | `price_low` | 오름차순 (쌀수록 위) | 실거래 DB (기존) | ✅ |
| 평균 평당가 | `pyeong_price_avg` | 오름차순 | 실거래 DB (기존) | ✅ |
| 준공연도 | `build_year` | 내림차순 (신축일수록 위) | 단지 DB (기존) | ✅ |
| 최근 거래건수 | `deal_count` | 내림차순 (활발할수록 위) | 실거래 DB (기존) | ✅ |
| 공원 도보 | `nearest_park_min` | 오름차순 | apt_walking_poi | ✅ |
| 지하철 도보 | `nearest_subway_min` | 오름차순 | apt_walking_poi | ✅ |
| 마트/편의점 도보 | `nearest_mart_min` | 오름차순 | apt_walking_poi | ✅ |
| 초등학교 도보 | `nearest_elementary_min` | 오름차순 | apt_walking_poi (**신규**) | ❌ |
| 중고등학교 도보 | `nearest_mid_high_min` | 오름차순 | apt_walking_poi (**신규**) | ❌ |
| 집→대중교통 도보 | `walk_to_transit_min` | 오름차순 (짧을수록 위) | transit_routes step1 (**신규**) | ❌ |
| 세대수 | `kaptdaCnt` | 내림차순 (대단지일수록 위) | 단지 DB (기존 필드, **정렬 신규**) | ❌ |
| 환승 횟수 | `transfer_count` | 오름차순 (적을수록 위) | `bus_cnt + subway_cnt` 계산 (**신규**) | ❌ |
| 실제 평수 | `pyeong` | 내림차순 (넓을수록 위) | 실거래 DB (기존 필드, **정렬 신규**) | ❌ |

> **참고**: 기존 `nearest_school_min`(초중고 통합)은 초등/중고 분리로 교체. 서버 필드 삭제, AC1 갱신.

---

## 4. Functional Requirements

### 서버 (app/search.py)
- F1. `apt_walking_poi` 집계 쿼리(4e 단계) 수정:
  - ~~`nearest_school_min`: `poi_lclas_cd = 'A'`~~ → 삭제
  - `nearest_elementary_min`: `poi_lclas_cd = 'A' AND poi_nm LIKE '%초등%'` 최솟값
  - `nearest_mid_high_min`: `poi_lclas_cd = 'A' AND poi_nm NOT LIKE '%초등%'` 최솟값
  - `nearest_park_min`, `nearest_subway_min`, `nearest_mart_min` 유지
- F2. POI 데이터 없는 단지는 `null` 반환 (정렬 시 맨 뒤로)
- F3. `_card_to_dict()`에 `walk_to_transit_min` 추가:
  - steps 배열에서 **첫 번째 step**이 `'도보'` 타입이면 해당 `time_min` 값 사용
  - 첫 step이 도보가 아니면 `null` (집 바로 앞에 정류장이 있는 케이스)
- F4. `transfer_count`는 서버 필드 불필요 — 프론트엔드에서 `card.bus_cnt + card.subway_cnt`로 계산

### 프론트엔드 (web/result.html)
- F5. 카드 목록 상단에 정렬 바 렌더링: `[1순위 ▾] [2순위 ▾] [3순위 ▾] [초기화]`
- F6. 각 드롭다운 옵션 = 정렬 항목 14개 + "선택 안 함"
- F7. 1순위에서 선택된 항목은 2·3순위 드롭다운에서 비활성(disabled) 처리
- F8. 2순위에서 선택된 항목은 3순위 드롭다운에서 비활성 처리
- F9. 드롭다운 변경 시 카드 배열 즉시 재정렬 (DOM 재렌더링)
- F10. `null` 값 카드는 해당 기준에서 맨 뒤로 정렬
- F11. 초기화 버튼 클릭 시 원래 서버 응답 순서로 복원
- F12. `transfer_count` 정렬 시 `card.bus_cnt + card.subway_cnt` 값으로 비교

---

## 5. UI 레이아웃

### 5-1. 페이지 내 위치

```
left-panel
├── fav-tabs          ← 기존 (전체 / ♥ 찜)
├── sort-bar          ← ★ 신규 삽입
└── cards-panel       ← 기존 카드 목록
```

`fav-tabs` 바로 아래, 카드 목록 바로 위에 고정 배치.  
카드를 스크롤해도 `sort-bar`는 `left-panel` 상단에 sticky로 고정.

---

### 5-2. sort-bar 외형

```
┌──────────────────────────────────────────────────────┐
│  정렬순서                               [초기화]       │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐  │
│  │ 1순위         │ │ 2순위         │ │ 3순위         │  │
│  │ 통근시간    ▾ │ │ 최저가      ▾ │ │ 선택 안 함  ▾ │  │
│  └──────────────┘ └──────────────┘ └──────────────┘  │
└──────────────────────────────────────────────────────┘
```

- 각 드롭다운에 작은 라벨(1순위 / 2순위 / 3순위)이 위에 붙어있음
- 초기화 버튼은 오른쪽 정렬, 텍스트 버튼 스타일 (배경 없음)
- 배경: 흰색, 하단 border 구분선으로 카드 목록과 분리

---

### 5-3. 드롭다운 옵션 목록

각 드롭다운은 동일한 항목 목록을 가짐.  
단, 상위 순위에서 이미 선택된 항목은 `disabled` 처리됨.

```
[ 선택 안 함  ]   ← 기본값 (아무 정렬 기준 없음)
─────────────
  통근시간
  최저 거래가
  평균 평당가
  준공연도
  최근 거래건수
  세대수
  실제 평수
  환승 횟수
─────────────
  집→대중교통 도보
  공원 도보
  지하철 도보
  초등학교 도보
  중고등학교 도보
  마트/편의점 도보
```

구분선(─)으로 "단지·거래 필드"와 "도보 거리 필드" 두 그룹으로 나뉨.

---

### 5-4. disabled 연동 동작 예시

```
1순위: [통근시간 ▾]      → 2순위, 3순위에서 "통근시간" disabled
2순위: [초등학교 도보 ▾] → 3순위에서 "초등학교 도보" disabled
3순위: [세대수 ▾]        → (더 이상 하위 없음)

결과: 카드가 통근시간 → 초등학교 도보 → 세대수 순으로 정렬됨
```

2순위를 "선택 안 함"으로 바꾸면 → 3순위도 자동으로 "선택 안 함"으로 초기화되고 disabled.

---

### 5-5. 정렬 방향 (고정, 토글 없음)

| 항목 | 방향 | 의미 |
|---|---|---|
| 통근시간 | 오름차순 | 짧을수록 위 |
| 최저 거래가 | 오름차순 | 쌀수록 위 |
| 평균 평당가 | 오름차순 | 쌀수록 위 |
| 준공연도 | 내림차순 | 신축일수록 위 |
| 최근 거래건수 | 내림차순 | 거래 활발할수록 위 |
| 세대수 | 내림차순 | 대단지일수록 위 |
| 실제 평수 | 내림차순 | 넓을수록 위 |
| 환승 횟수 | 오름차순 | 환승 적을수록 위 |
| 도보 관련 전체 | 오름차순 | 가까울수록 위 |

POI 데이터 없는 단지(`null`)는 해당 기준에서 항상 맨 뒤로.

---

## 6. Acceptance Criteria

### 기 완료 (AC1~AC6)
- [x] AC1. `/api/search` 응답 카드에 `nearest_park_min`, `nearest_subway_min`, `nearest_mart_min` 필드 포함
- [x] AC2. 정렬 바가 카드 목록 상단에 표시됨
- [x] AC3. 1순위 "통근시간" 선택 시 2·3순위 드롭다운에서 "통근시간" 항목이 disabled 상태
- [x] AC4. 다중 기준 정렬 결과가 올바름 (1순위 동점 시 2순위 적용, 2순위 동점 시 3순위 적용)
- [x] AC5. null 값 카드는 해당 정렬 기준에서 항상 맨 뒤
- [x] AC6. 초기화 버튼 클릭 시 원래 순서 복원

### 미구현 (신규 확장)
- [x] AC7. `/api/search` 응답 카드에 `nearest_elementary_min`, `nearest_mid_high_min`, `walk_to_transit_min` 필드 포함
- [x] AC8. 드롭다운 옵션에 초등학교 도보, 중고등학교 도보, 집→대중교통 도보, 세대수, 환승 횟수, 실제 평수 항목 표시
- [x] AC9. "초등학교 도보" 기준 정렬 시 `nearest_elementary_min` 오름차순 적용, null 단지는 맨 뒤
- [x] AC10. "집→대중교통 도보" 기준 정렬 시 `walk_to_transit_min` 오름차순 적용
- [x] AC11. "환승 횟수" 기준 정렬 시 `bus_cnt + subway_cnt` 오름차순 적용
- [x] AC12. 기존 "학교 도보" 항목이 드롭다운에서 제거되고 초등/중고로 대체됨

---

## 7. 구현 메모

### 완료 분
- `app/search.py`: `_card_to_dict()`에 `poi_min_map` 파라미터 추가. kaptCode 기준 `apt_walking_poi` 집계 쿼리(CASE WHEN)로 4개 필드 주입.
- `web/result.html`: `fav-tabs`와 `cards-panel` 사이에 `sort-bar` div 삽입. `renderCards()` 마지막에 `initSortBar()` 호출.
- 정렬 활성 시: 버킷 그룹 구조 대신 flat 리스트(`_renderSortedFlat`)로 전환. 지도 핀은 그대로 유지.
- 모든 순위 "선택 안 함" 시: `renderCards()` 재호출로 원래 버킷 뷰 복원.

### 미구현 분 (구현 포인트)
- `app/search.py` 4e 단계: `nearest_school_min` CASE WHEN 제거 → `nearest_elementary_min`(`LIKE '%초등%'`), `nearest_mid_high_min`(`NOT LIKE '%초등%'`) 2개로 교체
- `app/search.py` `_card_to_dict()`: `walk_to_transit_min` 추출 — `steps[0]['type'] == '도보'`이면 `steps[0]['time']`, 아니면 `None`
- `web/result.html` `SORT_OPTIONS` 배열: `nearest_school_min` 제거, 신규 6개 항목 추가
- `transfer_count`는 서버 필드 불필요 — JS에서 `card.bus_cnt + card.subway_cnt`로 계산
