# Spec: 로컬 데모 모드 (Local Demo Mode)

> **상태**: Implemented
> **작성일**: 2026-06-13
> **구현 브랜치**: claude/happy-curie-e7ry0s

---

## 1. Why (왜 만드는가)

- MANIFESTO 연결: "데이터가 없으면 말하지 않는다"의 개발 환경 버전 —
  실제 API 키·운영 DB 없이도 **진짜 파이프라인**(검색→추천→카드 렌더링)을
  로컬에서 끝까지 눈으로 확인할 수 있어야 한다. mock 응답이 아니라
  실데이터와 동일한 형태의 시드 데이터를 DB에 넣고, 코드는 운영과 동일하게 동작한다.
- 사용자(개발자)가 얻는 가치:
  - 신규 기여자/리뷰어가 키 발급 없이 `bash scripts/run_demo.sh` 한 번으로
    배포본과 동일한 화면을 로컬 URL로 확인
  - UI 작업(result.html 등) 시 ODsay/Kakao 호출·비용 0으로 반복 확인 가능
- Why Tree 계층: 직접적 제품 기능이 아닌 **개발 인프라** — 모든 Middle Why의
  구현·검증 속도를 높이는 토대.

---

## 2. User Story

```
As a BADUGI 개발자/리뷰어,
I want to API 키와 운영 데이터 없이 로컬에서 전체 화면 플로우를 띄우고 싶다,
so that 배포 환경과 동일한 모습을 즉시 확인하고 UI/로직 변경을 검증할 수 있다.
```

---

## 3. Scope

### In-scope
- `scripts/seed_demo_data.py`: 강남역 직장(wp_id=1) 기준 데모 SQLite DB 생성
  (apartments / kapt_complexes / trade_recent / trade_history / transit_cache /
  transit_routes / apt_pt_friend_comment / trade_tags / apt_walking_poi / workplaces)
- `app/workplaces.py`: `BADUGI_DEMO=1` 환경변수일 때 **DB에 이미 있는
  address_input/address_norm 정확 일치 행**을 Kakao 호출 없이 반환하는 우회 게이트
- `scripts/run_demo.py`(크로스 플랫폼) / `scripts/run_demo.sh`(macOS·Linux):
  .env(더미) 생성 → 시드 → uvicorn 기동 원커맨드 런처

### Out-of-scope (Non-goals)
- ODsay/Kakao/Anthropic 응답 자체의 mock — 시드에 없는 주소는 평소처럼
  실패를 솔직히 반환한다 (절대 규칙 4 유지)
- 친구 채팅(/chat)·웹검색 데모 — ANTHROPIC_API_KEY가 실제로 필요하므로 제외.
  키가 있으면 데모 DB 위에서도 그대로 동작한다.
- Vercel/Supabase 환경 — 데모 모드는 로컬 SQLite 전용

---

## 4. Functional Requirements

- F1. `python scripts/seed_demo_data.py` 실행 시 `DB_PATH`(기본 data/apartment.db)에
  스키마 + 데모 데이터를 멱등하게 생성한다 (재실행 시 기존 데모 행 교체).
- F2. 데모 데이터는 실제 파이프라인을 통과해야 한다:
  통근버킷 4개(≤30/30-40/40-50/50-60분) × 평형(20/30평대)에 카드가 분포하고,
  추천 슬롯·why-tags·가격변동 배지·친구 코멘트·경로 상세·단지 상세 3탭·POI가
  모두 표시된다.
- F3. `BADUGI_DEMO=1`일 때 `get_or_create()`는 Kakao 호출 전에
  `workplaces.address_input` 또는 `address_norm` 정확 일치 행을 찾으면 그 행을
  반환한다. 불일치 시 기존 경로(Kakao 호출)로 진행한다.
- F4. `BADUGI_DEMO` 미설정 시 동작은 기존과 100% 동일하다 (운영 영향 0).
- F5. `python scripts/run_demo.py`(또는 `bash scripts/run_demo.sh`) 한 번으로 .env 더미 생성(없을 때만) → 시드 →
  `http://localhost:8000` 기동까지 완료된다.

---

## 5. Non-functional Requirements

- **성능**: 시드 전부 transit_cache passed_filter=1 → 검색 시 ODsay 호출 0건,
  응답 1초 미만
- **보안**: 데모 게이트는 환경변수 명시 옵트인. 더미 키는 .env에만 존재, 커밋 금지
- **신뢰성**: 시드에 없는 주소 검색 → 기존 "주소 변환 실패" 400 에러 그대로 노출
- **호환성**: 로컬 SQLite 전용 (Postgres에서는 시드 스크립트 실행 거부)

---

## 6. UX / Vibe

- 데모 데이터의 친구 코멘트도 실제 톤 규칙(카톡 톤, 2문장/80자, 장점+단점)을 따른다
- 단지명은 가상의 이름을 사용하되 실제 데이터로 오인되지 않도록
  시드 스크립트 주석과 본 spec에 가상 데이터임을 명시한다

---

## 7. Data Model

신규 테이블 없음. 기존 런타임 테이블에 데모 행 삽입:

```
workplaces        : wp_id=1 강남역 (37.4979, 127.0276)
apartments        : DEMO001~DEMO010 (역삼·서초·잠실·신림 등 좌표 분산, 가상 단지)
kapt_complexes    : 단지별 상세 (세대수·층수·주차·난방·지하철)
trade_recent      : 카드용 최근 3개월 개별 거래행
trade_history     : 12개월 이력 (시세 차트 + 가격변동 배지용)
transit_cache     : 셀 × wp_id=1, passed_filter=1 (ODsay 호출 차단)
transit_routes    : rank 1~2, step1~3 (지하철/버스/도보)
apt_pt_friend_comment : 전 카드 코멘트 사전 시드 (llm_pending=false)
trade_tags        : 일부 단지 floor/price_chg 태그
apt_walking_poi   : 단지별 도보 POI 4~6개
```

---

## 8. API / Interface

신규 엔드포인트 없음.

```bash
# 원커맨드
bash scripts/run_demo.sh            # .env 생성(없으면) + 시드 + uvicorn 기동

# 개별 실행
python scripts/seed_demo_data.py    # 시드만
BADUGI_DEMO=1 uvicorn app.main:app --port 8000
# → http://localhost:8000/ 에서 '강남역' 검색
```

---

## 9. Edge Cases

| 케이스 | 기대 동작 |
|---|---|
| 시드에 없는 주소 검색 | Kakao 경로 진행 → 더미 키면 400 "주소 변환 실패" (정직한 실패) |
| DATABASE_URL 설정 상태에서 시드 실행 | 즉시 중단 + 안내 (운영 DB 오염 방지) |
| 시드 재실행 | DEMO 행 삭제 후 재삽입 (멱등) |
| BADUGI_DEMO 미설정 | 기존 동작과 완전 동일 |
| ANTHROPIC_API_KEY 더미 | 코멘트가 전부 사전 시드되어 LLM 호출 자체가 발생하지 않음 |

---

## 10. Acceptance Criteria

- [x] AC1: `bash scripts/run_demo.sh` 후 `/result.html?...강남역...`에서 추천 카드
      포함 8장이 버킷 3개(≤30/30~40/40~45분)에 분포해 렌더링된다
      (60분 입력 → 통근 버퍼 적용 유효 45분 — 운영과 동일 동작)
- [x] AC2: 카드에 친구 코멘트·why-tags·가격변동 배지가 표시되고 llm_pending=false
- [x] AC3: 단지 상세 3탭(정보/시세·거래/주변시설)과 경로 상세가 데이터와 함께 열린다
- [x] AC4: `BADUGI_DEMO` 미설정 시 전체 테스트 스위트 회귀 없음
- [x] AC5: 시드 스크립트는 DATABASE_URL(Postgres) 환경에서 실행을 거부한다
- [x] 로컬(SQLite) 환경에서 동작 (Vercel은 out-of-scope)

---

## 11. Open Questions

- Q1: 데모 단지 수를 늘려 스크롤·클러스터 동작까지 검증할가? → 추후 필요 시 확장
- Q2: 친구 채팅 데모용 stub 추가 여부 → 절대 규칙 4(mock 금지)와 충돌, 보류

---

## 12. 구현 메모 (Implement 후 채우기)

- 변경된 파일: `app/workplaces.py`(데모 게이트), `scripts/seed_demo_data.py`(신규),
  `scripts/run_demo.sh`(신규), `tests/test_workplaces.py`(게이트 테스트 추가)
- 주요 결정 사항:
  - 게이트는 `get_or_create()` 진입부 5줄 — resolve() 자체는 건드리지 않음
  - grid_key는 `app.transit.cell_of()`를 import해 계산 (수기 하드코딩 금지)
  - 친구 코멘트 사전 시드로 ANTHROPIC 키 불필요화
- 알려진 제약: 외부 CDN(Kakao Maps SDK·Daum postcode) 차단 환경에서는 지도가
  비어 보일 수 있음 — 카드/통계/모달은 정상 동작
