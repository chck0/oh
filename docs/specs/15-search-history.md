# Spec 15 — 최근 검색 직장 히스토리 (Search History)

**상태:** ✅ Implemented
**작성일:** 2026-05-27
**구현 브랜치:** hjkang83
**관련 spec:** 01 (search-input), 02 (search-pipeline), 13 (dual-workplace)

---

## 1. Why

- `workplaces` 테이블에 `last_used`, `search_count` 컬럼이 이미 존재함 — 재검색 히스토리 기반 데이터 준비 완료.
- 매일 같은 회사 주소를 다시 입력하는 마찰이 가장 큰 UX 병목.
- 직장 주소는 거의 변하지 않으므로 히스토리 1클릭 재검색이 사실상 홈 화면 역할을 할 수 있음.

---

## 2. User Story

```
As a 재방문 사용자,
I want to 직장 주소 입력란 아래에서 최근 검색 목록을 볼 수 있고,
so that 다시 타이핑하거나 주소 찾기 팝업 없이 1클릭으로 재검색할 수 있다.
```

---

## 3. Functional Requirements

- **F1**: `GET /api/workplaces/recent?limit=5` — search_count DESC, last_used DESC 정렬, 최대 10개 제한
- **F2**: 응답: `[{address_input, address_norm, search_count, last_used}]`
- **F3**: search.html W1 주소 입력란 아래에 최근 검색 칩 표시 (페이지 로드 시 자동 호출)
- **F4**: 칩 클릭 → 해당 입력란에 `address_input` 자동 입력 (submit은 수동)
- **F5**: 결과 0개 또는 API 실패 시 칩 영역 미표시 (graceful degradation)
- **F6**: W1 칩이 W2 입력란에도 재사용 가능 (같은 히스토리 데이터)
- **F7**: 백엔드 `workplaces` 스키마 변경 없음 (기존 컬럼 활용)

---

## 4. Acceptance Criteria

- [x] AC1: `GET /api/workplaces/recent` 200 응답, 배열 반환
- [x] AC2: `search_count DESC, last_used DESC` 정렬
- [x] AC3: `limit` 쿼리 파라미터 1~10 범위 강제
- [x] AC4: search.html 로드 시 칩 자동 표시 (DB에 데이터 있을 때)
- [x] AC5: 칩 클릭 시 주소 입력란에 값 자동 입력
- [x] AC6: API 오류 / 결과 0개 시 칩 영역 미표시
- [x] AC7: 기존 테스트 360개 전체 통과 (회귀 없음)

---

## 5. 구현 메모

> **구현 완료**: 2026-05-27

- `app/main.py`: `GET /api/workplaces/recent` 엔드포인트 추가
- `web/search.html`: 페이지 로드 시 fetch → 칩 렌더링, 클릭 시 입력값 자동 설정
- `tests/test_search_history.py`: 신규 테스트
