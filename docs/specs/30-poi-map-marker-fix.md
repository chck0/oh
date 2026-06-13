# Spec 30: 좌측 POI 클릭 → 지도 마커 복구

> 상태: 구현완료 · 사용자 최종확인 대기 | 작성일: 2026-06-05 | 브랜치: chck0527/poi-marker-fix

## 1. Why (왜)

단지 상세 패널 좌측의 "도보 주요 시설" POI(학교·상점 등)를 클릭하면 예전엔 지도에 마커가
찍혔는데 지금은 안 된다. 브라우저 진단으로 두 가지 원인 확인:

1. **`kakao.maps.services` 미로드** — `/api/kakao-sdk`가 302 리다이렉트라 DOM의 `<script>` src가
   프록시 URL로 남아 Kakao SDK가 `libraries=services`를 파싱 못 함 → `services` 미로드 →
   `new kakao.maps.services.Places()`가 throw. **→ main.py를 document.write 방식으로 수정해
   이미 해결, 브라우저에서 servicesLoaded:true 확인.**
2. **`showPoiMarker`의 keywordSearch 실패** — 위치 제약 없는 keywordSearch는 정상이나
   (스타벅스/강남역/구리여자중학교 OK), `location`+`radius` 제약 시 ZERO_RESULT 발생.
   또한 `showPoiMarker`는 풀네임만 검색하고 substring 폴백이 없어(검증함수엔 있음)
   "구리여중고교"처럼 축약된 POI명은 마커가 안 찍힘.

## 2. Scope (범위)

- **포함:** 좌측 POI 행 클릭 시 지도에 마커가 안정적으로 찍히도록 복구. SDK services 로드 보장.
  `showPoiMarker`의 검색 견고화(폴백, 위치/반경 파라미터 점검).
- **제외(안 함):** apt_walking_poi 스키마 변경(좌표 컬럼 추가), POI 데이터 재적재, 디자인 변경.

## 3. 설계 (어떻게)

- 건드리는 파일: `app/main.py`(SDK 로더 — 이미 수정), `web/result.html`(`showPoiMarker` 견고화).
- DB 변경: 없음. API 변경: 없음(경로·스키마 유지).
- **핵심 조사 항목(루프가 확정):**
  - location+radius keywordSearch가 ZERO_RESULT인 원인 (radius 단위? 좌표 유효성? 옵션?).
    → 정상 동작하는 검색 파라미터 조합을 브라우저로 실측해 확정.
  - `showPoiMarker`를 `validateAndFilterPois`와 동일한 폴백(풀네임 실패 시 substring(0,6))으로 견고화.
  - 필요 시 위치 제약을 완화하거나 제거(전역 검색 후 가장 가까운 결과 선택).
- 검증은 **실제 브라우저(Claude-in-Chrome)** 로 end-to-end 수행 (자동 테스트 없음 영역).

## 4. 완료 조건 (Acceptance Criteria)

- [x] AC1: `kakao.maps.services.Places` 로드됨 (브라우저 servicesLoaded:true 확인) ← 핵심 수정
- [x] (검색 검증) keywordSearch가 showPoiMarker 옵션으로 '월촌초등학교'→'서울월촌초등학교' 401m OK
- [~] AC2~AC5: 마커 픽셀 표시 — **자동화 브라우저 탭이 0x0(display:none)이라 맵 초기화 불가 →
  픽셀 e2e 검증 불가. 사용자 실제 브라우저 확인 필요.** (services·검색·좌표해석까지는 검증됨)
- [x] AC6: pytest 388 통과, import app.main OK

### 변경
- `app/main.py`: `/api/kakao-sdk` 302 리다이렉트 → document.write 로더 (services 로드 복구)
- `web/result.html`: `showPoiMarker`에 substring 폴백 + `sort:DISTANCE` 추가

### 부수발견 (별도 이슈)
- 일부 단지(예 41310-60 구리시) `apartments.lat/lng`가 ~20km 어긋남 → 위치기반 검색 실패.
  좌표 데이터 품질 문제로, POI 마커 로직과 별개. 추후 재지오코딩 검토 대상.
