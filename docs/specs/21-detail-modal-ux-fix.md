# Spec 21 — 단지 상세 모달 UX 수정 (POI 카테고리 + 거래 평형 그룹화)

**상태:** ✅ Implemented
**작성일:** 2026-05-28
**구현 브랜치:** hjkang83
**관련 spec:** 17 (apt-detail-modal), 19 (panel-resize-poi-map-marker)

---

## 1. Why

- "주변시설" 탭에서 "CU" → `중학교`, "대한권투체육관" → `도서관` 등 카테고리 레이블이 전혀 맞지 않음.  
  원인: `_renderDetail()`이 구형 `POI_LABEL` 매핑(A=공원·B=버스 등) 사용 — 실제 DB 코드(A=학교·D=교통 등)와 불일치.  
  하단에 정확한 `POI_CAT_NAME` / `POI_ALLOWED_SUBS` 가 이미 정의되어 있으나 연결 안 됨.
- "시세·거래" 탭에서 20평대·30평대 거래가 섞여서 나열 — 평형별 비교가 불가능해 혼란.

---

## 2. Scope

### In-scope
- `_renderDetail()` 내 주변시설 탭: 잘못된 `POI_LABEL` 제거 → `POI_CAT_NAME` / `POI_ALLOWED_SUBS` / `POI_ORDER` 재사용, 카테고리별 그룹 헤더 표시
- `_renderDetail()` 내 시세·거래 탭: `pyeong_type` 기준 그룹화 후 각 그룹에 헤더 표시
- 기존 POI 마커 클릭 기능(`togglePoiMarker`) 유지

### Out-of-scope
- 백엔드 변경 없음
- POI 데이터 자체 수정 없음
- 거래 필터(특정 평형만 보기) UI — 그룹화로 충분

---

## 3. Functional Requirements

- **F1**: 주변시설 탭 — `POI_ALLOWED_SUBS` 필터 적용 후 `POI_ORDER` 순으로 카테고리 그룹화
- **F2**: 각 카테고리 그룹 헤더(`.dp-poi-category` 스타일) 표시, 그룹당 최대 5개 시설
- **F3**: 각 시설 행은 클릭 시 지도 마커 토글(기존 `togglePoiMarker` 유지)
- **F4**: 시세·거래 탭 — 거래 내역을 `pyeong_type` 기준으로 그룹화
- **F5**: 각 평형 그룹에 헤더 표시, 그룹당 최대 8건 표시
- **F6**: 거래 행 컬럼을 3열(날짜·금액·층)로 변경 — 평형은 그룹 헤더로 표현

---

## 4. Acceptance Criteria

- [x] AC1: "주변시설" 탭 카테고리 레이블이 실제 시설 유형과 일치 (CU → 쇼핑/편의 그룹)
- [x] AC2: 카테고리 그룹 헤더가 `POI_ORDER` 순서로 표시됨 (교통 → 학교 → 어린이집 순)
- [x] AC3: `POI_ALLOWED_SUBS` 필터로 오분류 데이터(주유소·아파트단지 등) 제외됨
- [x] AC4: POI 마커 클릭 기능 정상 동작
- [x] AC5: "시세·거래" 탭에서 평형대별로 거래가 그룹화되어 표시됨
- [x] AC6: 기존 테스트 회귀 없음

---

## 5. 구현 메모

- **변경 파일**: `web/result.html` 만 수정 (백엔드 변경 없음)
- `_renderDetail()` 내 POI 섹션: 구형 `POI_LABEL` const 삭제 → `POI_ORDER` / `POI_CAT_NAME` / `POI_ALLOWED_SUBS` (스크립트 하단 정의) 참조
- `_renderDetail()` 내 거래 섹션: `pyeong_type` 기준 `tradeGroups` 객체로 그룹화 → 그룹 헤더 + 3열 grid
- `.dp-poi-category` 기존 CSS 재사용 (거래 그룹 헤더에도 동일 스타일 적용)
