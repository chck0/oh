# AGENTS.md — BADUGI

> 이 파일은 AI 에이전트가 BADUGI 코드베이스를 다룰 때 참조하는 운영 규칙서다.
> CLAUDE.md(기술 설정)와 쌍으로 읽는다.

---

## Project: BADUGI

"부동산 잘 아는 친구가 카톡으로 추천해주는" 아파트 추천 서비스.
직장 주소 입력 → 대중교통 통근시간 기반 추천 → Claude AI 코멘트.

---

## 1. Core Persona & Target User

### 핵심 타겟
**"부동산을 한두 번 알아본 30대 1인 가구 첫 집 구매자"**

- 이미 예산 범위는 대략 알지만, 어느 동네를 봐야 할지 모름
- 직방·호갱노노를 돌아다니다 정보에 압도됨
- 중개사 추천은 믿기 어렵고, 스스로 판단 근거가 필요함
- 5분 내로 "이 집은 왜 싼지"까지 파악하고 싶음

### 타겟에서 의도적으로 제외
| 제외 대상 | 이유 |
|---|---|
| 갈아타기 투자자 | 학군·재건축·GTX 호재가 주요 기준 → 통근시간 우선 모델과 어긋남 |
| 맞벌이 (기본) | Dual Workplace(spec-13)로 부분 지원하나, 핵심 타겟 아님 |
| 초보 (예산 모르는 단계) | "얼마까지 살 수 있는지" 단계가 선행 필요 |

### 유저 인터뷰 핵심 교훈 (2026-05, 5인 인터뷰)
1. **신뢰 > 속도**: 사용자가 이탈하는 원인은 느린 로딩이 아니라 "왜 이 가격?"에 대한 답 부재. → Why-price 태그(spec-11) 의무 노출.
2. **포지셔닝 결정**: 통근시간 단일 우선은 약점이 아닌 포지셔닝. 타겟 확장 시 적합성 빠르게 하락.
3. **정보 최소주의**: 숙련자는 거부감, 초보자는 "뭘 입력해야 할지 모름". 스위트스폿은 좁다.

---

## 2. Agent Constraints & Rules

### 절대 규칙
1. **Spec First**: 어떤 기능도 `docs/specs/NN-*.md` 없이 코드를 먼저 짜지 않는다.
2. **공공데이터 원칙**: 출처 불명의 호재·학군 정보를 단정하지 않는다. 웹 검색 결과에는 반드시 출처 URL을 포함한다.
3. **파괴적 명령 인간 승인**: 파일 삭제, 외부 이메일/메시지 발송, DB 테이블 DROP은 반드시 사용자 확인 후 실행한다.
4. **모르면 모른다고 한다**: API 응답이 없거나 데이터가 불충분하면 mock으로 채우지 않고 오류/빈값을 솔직히 반환한다.
5. **테스트 → 커밋 순서**: 커밋 전 `python -m pytest tests/ -q` 통과 필수. 회귀 시 커밋 중단.

### 코딩 규칙
- SQLite(로컬) ↔ Postgres(Vercel)는 `DATABASE_URL` 유무로 자동 전환. 방언 차이는 `app/portable.py`에서 처리.
- Vercel 서버리스 60초 제약: 신규 직장 첫 검색은 `partial=true`로 빠르게 반환, 재검색 시 캐시 채움.
- pgBouncer Transaction mode: `prepared_statement=False`, `except` 블록에 `conn.rollback()` 필수.
- LLM 역할 분리: 추천 카드 → `claude-sonnet-4-6`, 일반 카드 → `claude-haiku-4-5`. 동시 Haiku 호출 8개 이하 제한.
- `result.html` 신규 DOM 요소 추가 시 `.result-layout` grid 자식 구조 영향 확인 필수.
- 웹 검색(DuckDuckGo) 실패 시 graceful degradation — "공식 확인이 필요해" 안내, 500 에러 금지.
- localStorage 상태: favorites(♥), search history(최근 직장), chat history(24시간) — 서버 저장 없음.

### 검색 API 파라미터 (POST /api/search)
| 파라미터 | 타입 | 설명 | 관련 spec |
|---------|------|------|-----------|
| `address` | str | 직장 주소 | spec-01 |
| `max_min` | int | 최대 통근시간(분) | spec-01 |
| `max_price` | int | 최대 예산(만원) | spec-01 |
| `min_price` | int | 최소 예산(만원) | spec-09 |
| `pyeong_types` | list | 평형 필터 (20평대 등) | spec-01 |
| `build_year_min` | int | 준공연도 하한 | spec-07 |
| `address_2` | str | 두 번째 직장 주소 (맞벌이) | spec-13 |
| `max_min_2` | int | 두 번째 직장 최대 통근시간 | spec-13 |

**주의**: `max_price` 범위가 넓을수록 ODsay 호출 셀 수 급증 → 504 위험. 범위 경고 UI 있음.

### 커밋 규칙
- Conventional Commits: `feat:`, `fix:`, `refactor:`, `docs:`, `perf:`, `test:`
- 브랜치: `hjkang83` → PR → squash merge → `main`
- 세션 시작 시 `git pull origin main` 필수

---

## 3. Project Map

```
app/
  search.py      # POST /api/search — 핵심 검색 파이프라인
  ai.py          # 통근버킷×평형 추천 로직 + Claude 코멘트 생성
  transit.py     # ODsay 멀티키 병렬 호출 + 경로 필터링 + DB 캐시
  workplaces.py  # Kakao 주소 정규화 + wp_id 발급
  db.py          # SQLite↔Postgres 이중 어댑터
  portable.py    # DB 비호환 로직 Python 구현 (upsert, returning 등)
  main.py        # FastAPI 진입점 + 미들웨어 + 진단 엔드포인트
  models.py      # Pydantic 요청/응답 스키마
api/
  index.py       # Vercel 서버리스 진입점
web/
  result.html    # 메인 결과 UI (지도 + 카드 + 친구 채팅 + 즐겨찾기)
  search.html    # 검색 조건 입력 + 최근 직장 히스토리 칩
docs/
  specs/         # 기능 스펙 (01~28, 다음: 29)
  manifesto.md   # 제품 철학
  whytree.md     # 핵심 설계 결정 근거 (Why 3단계)
  premortem.md   # 실패 시나리오 + 현재 대응 상태
wiki/            # 도메인 지식 아카이브
scripts/         # 데이터 파이프라인 + DB 마이그레이션
AGENTS.md        # 이 파일
CLAUDE.md        # 기술 스택 + 환경변수 + 세부 작업 규칙
```

### 핵심 데이터 흐름
```
직장 주소
  → Kakao REST API (좌표)
  → 반경 내 is_apt=1 단지 필터
  → ODsay 병렬 호출 (통근시간)
  → (버킷 × 평형) 슬롯 최저가 추천
  → Claude 코멘트 백그라운드 생성
  → cards + stats + buckets 응답
```

---

## 4. Known Traps (반복 실수 목록)

| 발견일 | 함정 | 대응 |
|--------|------|------|
| 2026-05 | `result-layout` grid 깨짐 — 새 div를 grid 직접 자식에 추가 | `grid-column`/`grid-row` 명시 |
| 2026-05 | `InFailedSqlTransaction` — rollback 없이 다음 쿼리 | `except` 블록에 `conn.rollback()` |
| 2026-05 | `UndefinedColumn` — `supabase_schema.sql` 업데이트했지만 Supabase `ALTER TABLE` 미실행 | Spec 구현 메모에 수동 마이그레이션 명시 |
| 2026-05 | 504 Timeout — `max_price` 범위 넓음 → 매칭 단지 폭증 → ODsay 셀 수 급증 | `MAX_FETCH_CELLS=200` + 범위 경고 UI |
| 2026-05 | lxml 의존 패키지(python-docx/pptx) Vercel 빌드 실패 | C 확장 의존 패키지 `requirements.txt` 추가 금지 |
| 2026-05 | 직접 검색 단지 지도 이동 불가 — `showDetail()`이 `resultData.cards`에서 lat/lng 조회 | `_openLookupDetail()`에서 `_isLookup:true` 플래그로 cards에 임시 삽입 (spec-26) |
| 2026-05 | onclick 인라인 핸들러에 특수문자 포함 아파트명 → JS 파싱 오류 | `addEventListener` 방식 또는 `data-*` 속성으로 교체 (spec-22) |
| 2026-05 | Haiku 동시 호출 rate limit | 동시 호출 8개 이하로 제한 |
| 2026-05 | trade_tags 미존재 테이블 SELECT → 500 연쇄 | graceful degradation + rollback 필수 |

---

## 5. Spec 번호 현황

다음 신규 Spec 번호: **29**

완료 목록: spec-01~28 (세부 내용 → `docs/specs/SPEC_GUIDE.md`)
