# Spec: 패널 리사이저 + 도보 시설 지도 마커

> **상태**: ✅ Implemented
> **작성일**: 2026-05-27
> **구현 브랜치**: feat/panel-resize-poi-marker

---

## 1. Why (왜 만드는가)

- 사용자마다 지도를 크게 보고 싶은 경우와 카드 목록을 많이 보고 싶은 경우가 다름 — 고정 비율은 한쪽을 희생시킴
- "도보 주요 시설" 목록은 텍스트로만 존재해 공간적 감이 없음 — 지도에서 위치를 직접 보면 입지 판단이 훨씬 빠름
- 사용자가 얻는 가치: 자기 취향에 맞게 화면 배분 조절 + "이 아파트 앞에 편의점이 진짜 가까운가?" 를 눈으로 확인

---

## 2. User Story

```
As a 직장인,
I want to 좌측 카드 패널과 지도 크기를 드래그로 조절하고,
도보 시설을 클릭하면 지도에 위치가 표시되길,
so that 내가 관심 있는 정보에 화면을 집중할 수 있고 입지를 직관적으로 파악할 수 있다.
```

---

## 3. Scope

### In-scope
- 데스크톱: `left-panel` ↔ `map-panel` 사이 드래그 핸들 (마우스)
- 도보 시설 아이템 클릭 → Kakao 지도에 POI 마커 표시
- POI 좌표 취득: 카카오 장소 검색 API (키워드 + 아파트 중심점 반경) 사용
- 마커 클릭 시 말풍선(시설명, 거리) 표시
- 선택된 시설 아이템 하이라이트

### Out-of-scope (Non-goals)
- 모바일 터치 리사이즈 (모바일은 세로 스택 레이아웃이라 불필요)
- 패널 크기 localStorage 저장 (세션 내 임시 사용으로 충분)
- POI 좌표를 DB에 영구 저장 (API 비용 고려해 런타임 조회)
- 여러 시설 동시 다중 선택

---

## 4. Functional Requirements

- F1. `result-layout` 두 패널 사이에 드래그 핸들(8px 폭) 표시
- F2. 핸들 드래그 시 `left-panel` 너비가 실시간으로 변경되고 지도가 리사이즈됨 (`kakaoMap.relayout()` 호출)
- F3. 최소 너비 제약: `left-panel` ≥ 280px, `map-panel` ≥ 320px
- F4. 카드 상세 패널 "도보 주요 시설" 탭의 각 시설 행(row)에 클릭 이벤트 추가
- F5. 클릭 시 카카오 장소 검색 API(`/v2/local/search/keyword.json`)로 시설명 + 아파트 좌표 기준 반경 500m 검색
- F6. 검색 결과 1순위로 카스텀 마커 생성 (카테고리별 색상 구분)
- F7. 마커 클릭 시 InfoWindow 표시: `{시설명} | 도보 {N}분 · {M}m`
- F8. 다른 시설 클릭 시 이전 POI 마커/InfoWindow 교체 (중첩 방지)
- F9. 상세 패널 닫힐 때 POI 마커 일괄 제거

---

## 5. Non-functional Requirements

- **성능**: 카카오 장소 검색은 클릭 시점 1회 호출 (미리 호출 X), 응답 < 300ms 목표
- **신뢰성**: 장소 검색 결과 없을 때 조용히 실패 (토스트 없이 무시)
- **호환성**: 데스크톱 Chrome/Safari, 1280px 이상 해상도 기준
- **비용**: 카카오 장소 검색 API 무료 쿼터(하루 300,000회) 내 운용

---

## 6. UX / Vibe

- 리사이즈 핸들: 호버 시 배경색 강조 + 양방향 화살표 커서(`col-resize`)
- POI 마커: 카테고리별 작은 원형 아이콘 (편의점=초록, 병원=빨강, 학교=파랑, 기타=회색)
- 클릭된 시설 행: 배경 `#F0F4FF` 하이라이트, 재클릭 시 마커 제거 (토글)
- InfoWindow: 기존 apt 말풍선 디자인 톤 유지 (흰 배경, 작은 폰트)

---

## 7. Data Model

```
apt_walking_poi (기존 — 변경 없음)
├── poi_lclas_cd: str   -- 대분류 코드
├── poi_mlsfc_cd: str   -- 중분류 코드
├── poi_nm: str         -- 시설명 (카카오 검색 키워드로 사용)
├── distance_m: int
└── walking_min: int

카카오 장소 검색 응답 (런타임, 저장 안 함)
├── x: str  -- 경도 (lng)
└── y: str  -- 위도 (lat)
```

영향받는 테이블: 없음 (DB 변경 없음)

---

## 8. API / Interface

```javascript
// 장소 검색 (프론트엔드 직접 호출 — 카카오 REST)
GET https://dapi.kakao.com/v2/local/search/keyword.json
  ?query={poi_nm}
  &x={apt_lng}&y={apt_lat}
  &radius=500
  &size=1
Header: Authorization: KakaoAK {KAKAO_REST_API_KEY}

// 지도 리사이즈 (Kakao Maps SDK)
kakaoMap.relayout()

// POI 마커 생성
new kakao.maps.Marker({ position: new kakao.maps.LatLng(y, x), map: kakaoMap })
new kakao.maps.InfoWindow({ content: '<div>...</div>' })
```

**주의**: 카카오 REST API 키는 프론트엔드에 노출됨 — 현재 Kakao Maps SDK 키와 동일 도메인 제한으로 보안 유지.

---

## 9. Edge Cases

| 케이스 | 기대 동작 |
|---|---|
| 장소 검색 결과 0건 | 마커 생성 안 함, 시설 행 하이라이트만 유지 |
| 카카오 API 오류 (rate limit 등) | 조용히 실패, 콘솔 경고만 출력 |
| 패널 최소 너비 도달 시 드래그 | 최솟값에서 멈춤, 더 이상 축소 안 됨 |
| 상세 패널 닫고 다른 카드 열기 | 이전 POI 마커 모두 제거 후 새 카드 렌더 |
| 모바일(767px 이하) | 리사이즈 핸들 숨김, POI 마커는 그대로 동작 |

---

## 10. Acceptance Criteria

- [x] AC1: 데스크톱에서 핸들 드래그 시 `left-panel` 너비가 실시간으로 변경됨
- [x] AC2: 드래그 후 지도가 새 크기에 맞게 재렌더링됨 (흰 공백 없음)
- [x] AC3: `left-panel` ≥ 280px, `map-panel` ≥ 320px 제약 적용됨
- [x] AC4: 도보 시설 행 클릭 시 지도에 마커가 표시됨
- [x] AC5: 마커 클릭 시 시설명 + 거리 InfoWindow 표시
- [x] AC6: 다른 시설 클릭 시 이전 마커 제거 후 새 마커 표시
- [x] AC7: 상세 패널 닫힐 때 POI 마커 모두 제거됨
- [x] AC8: 장소 검색 결과 없을 때 앱이 중단되지 않음

---

## 11. Open Questions

- Q1: 카카오 REST API 키를 프론트에서 직접 쓰는 게 현재와 동일한 보안 수준인가? (현재도 Kakao Maps SDK 키가 HTML에 노출돼 있으므로 동일 수준)
- Q2: POI 좌표를 `apt_walking_poi` 테이블에 컬럼 추가해 저장하면 API 호출 없앨 수 있음 — 데이터 파이프라인 업데이트 비용 vs. API 호출 비용 trade-off

---

## 12. 구현 메모

- **변경된 파일**: `web/result.html` (CSS + HTML + JS)
- **주요 결정 사항**:
  - 패널 리사이즈: CSS Grid → Flexbox로 전환 (`left-panel` 고정 width + `map-panel` flex:1)
  - POI 좌표 조회: REST API 직접 호출 대신 `kakao.maps.services.Places` SDK 사용 (CORS 문제 회피, `libraries=services` SDK URL 추가)
  - 재클릭 토글: `_activePoiRow === row` 비교로 같은 시설 재클릭 시 마커 제거
  - `openDetail()` 진입 시 `clearPoiMarker()` 호출 — 다른 카드 열 때 이전 마커 자동 제거
- **알려진 제약**: 모바일(≤767px)에서 리사이즈 핸들 CSS로 숨김, POI 마커는 정상 동작
