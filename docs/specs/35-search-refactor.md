# Spec 35: search.py 모듈 분할 리팩토링

> (구 spec-28 — 28-commute-economics와 번호 충돌로 35로 재배정)
> 상태: Implemented ✅ | 작성일: 2026-06-04 | 브랜치: chck0527/search-refactor

## 1. Why (왜)

`app/search.py`가 1592줄로 비대하다. 검색·단지상세·채팅 세 가지 책임이 한 파일에
뒤섞여 있어 수정/리뷰가 어렵고, 채팅 같은 신규 기능이 계속 붙으면서 더 커지는 중.
책임 단위로 분할해 각 파일을 읽고 고치기 쉽게 만든다. **동작은 1도 안 바뀐다 (순수 구조 변경).**

## 2. Scope (범위)

- **포함:** `search.py`를 책임별로 분할. import 정리. 모든 라우트 경로·응답 형태 그대로 유지.
- **제외(안 함):** 로직 변경, 성능 개선, 새 기능, API 시그니처 변경, 테스트 로직 수정.
  엔드포인트 URL/요청/응답 스키마는 한 글자도 안 바꾼다.

## 3. 설계 (어떻게)

현재 외부 결합: `app/main.py`만 `from app.search import router, _get_cached_apts` 사용.
→ `router` 집계와 `_get_cached_apts` 노출만 유지하면 바깥은 안 깨진다.

단계적 분할 (위험 낮은 순):
- **Phase 1 — `app/chat.py`**: 채팅 블록 추출 (`_chat_cache_get/set`, `_do_search`,
  `_extract_doc_text`, `_parse_reply`, `apt_chat` 라우트). ⚠️ 테스트 커버리지 0% → 수동 검증 필수.
- **Phase 2 — `app/detail.py`**: `apt_detail`, `search_apt_lookup`, `apt_routes` 라우트.
  (`test_detail_endpoint.py`가 커버 → 안전)
- **Phase 3 — `app/cards.py`**: 공용 헬퍼 `_card_to_dict`, `_build_transit_summary`.
  여러 모듈이 쓰므로 import 경로 정리.
- **Phase 4 — `search.py` 잔류**: `/search` 코어 + comments + `_get_cached_apts` + `_fetch_card_extras`.

각 새 파일은 자체 `APIRouter`를 갖고, `main.py`에서 등록하거나 `search.router`에 include.
- DB 변경: 없음
- API 변경: 없음 (경로·스키마 전부 유지)
- 핵심 엣지케이스: 순환 import (chat ↔ cards ↔ search). 공용 헬퍼는 `cards.py`로 모아 단방향 의존 유지.

## 4. 완료 조건 (Acceptance Criteria)

- [x] AC1: `python -m pytest` 388개 전부 통과 (베이스라인 동일)
- [x] AC2: `search.py` 1592줄 → **755줄** 로 감소 (800 이하 달성)
- [x] AC3: 채팅 엔드포인트 수동 검증 — `_parse_reply` 로직 + `/api/apt/{seq}/chat` 라우트 도달(404) 확인
- [x] AC4: 앱 정상 기동 + `/api/_debug` 응답 (DEBUG_API 미설정 시 "debug disabled" 게이팅 — 기존 동작)
- [x] AC5: 11개 라우트 URL·메서드 변경 0 (순수 구조 리팩토링)
- [x] AC6: 순환 import 없음 (`python -c "import app.main"` OK)

### 결과
- `app/search.py` 1592 → 755줄. 신규: `app/chat.py`(352) · `app/detail.py`(420) · `app/cards.py`(120).
- `main.py`는 `from app.search import router, _get_cached_apts` 그대로 (외부 무변경).
- `conftest.py` `_route_db_connect_to_override`가 `app.detail.db_connect`도 패치하도록 추가.
