# spec-43: 상세 패널 로딩 최적화

## 문제

아파트 카드 클릭 후 상세 패널이 열리기까지 두 가지 병목 존재:

1. **Backend — `_q_infra` 순차 실행**
   `detail.py`의 `_q_infra()`가 하나의 DB 커넥션에서 apt_slope → building_register 두 쿼리를 순차 실행.
   다른 7개 쿼리와 asyncio.gather에 묶여 있어도, 이 함수 안에서는 직렬이라 gather 전체의 병렬 효율이 감소.

2. **Frontend — `validateAndFilterPois()` 직렬 Kakao 호출**
   패널 렌더 직후 POI 행(최대 50개)마다 카카오 Places API를 1개씩 순차 호출.
   POI 30개 기준 약 6~12초간 목록이 계속 줄어드는 현상 발생. (비동기로 실행되지만 UX 저하)

## 해결 방향

### A. `_q_infra` 분리 (detail.py)

`_q_infra()`를 `_q_slope()` + `_q_br()` 두 함수로 분리해 asyncio.gather에 독립 태스크로 추가.
- 각자 db_connect()로 별도 커넥션 사용 → 진짜 병렬
- 기존 `infra = (slope_row, br_rows)` 구조는 호출부에서 그대로 유지

### B. `validateAndFilterPois()` 제거 (result.html)

사전 검증 호출 제거. 클릭 시 `showPoiMarker` → `fail()` 경로가 이미 존재하므로 동작 커버리지 동일.
- POI 클릭 시 카카오가 시설을 찾지 못하면 기존 `_poiNotice('지도에서 위치를 확인하지 못했습니다')` 그대로 표시
- 패널 로드 직후 목록 변동 없음 → 더 안정적인 UX

## 기대 효과

| 항목 | Before | After |
|------|--------|-------|
| backend gather | 7태스크 (infra 내부 2쿼리 직렬) | 8태스크 모두 독립 병렬 |
| POI 유효성 검증 | 패널 열릴 때마다 최대 ~12s 백그라운드 Kakao 호출 | 제거 (클릭 시 즉시 처리) |
| 패널 목록 안정성 | 수초간 POI 행이 사라지는 시각적 불안 | 즉시 확정 목록 표시 |

## 관련 파일

- `app/detail.py` — `_q_infra` 분리
- `web/result.html` — `validateAndFilterPois()` 함수 및 호출부 제거
