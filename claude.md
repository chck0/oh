## 프로젝트 개요

**BADUGI — 직장 주소 기반 아파트 추천 서비스.**
직장 주소 입력 → 반경 내 매물 필터 → ODsay 대중교통 경로 → 통근버킷 × 평형 매트릭스 추천 → Claude AI 코멘트.
배포: Vercel (서버리스) + Supabase Postgres.

## 작업 방식

### 0. Worklog + Spec (별개의 축)

둘은 양자택일이 아니다. 큰 작업은 **둘 다** 쓴다.

- **Worklog** (머지·인수인계용): 커밋할 때 **항상** 작성. 크기 무관. → 작성법은 아래 "작업 일지" 섹션.
- **Spec** (사전 설계용): **큰 작업에만** 추가로 작성 (여러 파일·새 DB 테이블·새 API·여러 Phase).
  - 작성법은 `docs/specs/_meta/GUIDE.md` (`_meta/template.md` 복사 → 4칸: **Why / Scope / 설계 / 완료 조건(= 루프 종료 기준)**)
  - 버그픽스·리팩토링·소규모 수정은 Spec 생략 (worklog는 그래도 씀).

### 1. 자율 루프 (OMC Ralph)

**아래 중 2개 이상 해당하면 AI가 먼저 `/oh-my-claudecode:ralph` 실행을 제안한다:**
- 수정 파일 5개 이상 / 새 DB 테이블·외부 API 연동 / 여러 Phase로 나뉘는 작업

**제안 형식 (질문은 최대 2개 — 완료 조건이 애매할 때만):**
```
🔁 루프 제안
목표: ...
단계: 1) ... 2) ... 3) ...
완료 조건: 모든 엔드포인트 정상 응답 + 기존 테스트 통과
금지 사항: .env 수정 금지, DB 스키마 삭제 금지
```

**루프 중 원칙:** 사용자 확인 없이 계속 진행 (테스트가 안전망). 중단: `/oh-my-claudecode:cancel`

### 2. 큰 그림 먼저

작업 시작 시 영향받는 파일 목록을 먼저 정리한 뒤 구현 진입. 모호하면 추정하지 말고 질문.

### 3. 테스트 → 커밋

커밋 전 `uvicorn app.main:app --reload` 기동 확인. `/api/_debug` · `/api/_test_odsay` · `/api/_test_kakao` 로 상태 체크.

### 4. Git 커밋

커밋 메시지: `feat:` · `fix:` · `refactor:` · `docs:` · `perf:`. merge·rebase·push는 명시적 요청 시만.

## 기술 스택

- **백엔드**: Python 3.10+ / FastAPI + uvicorn
- **DB**: `DATABASE_URL`이 `postgresql://` → Supabase 모드 / 파일 경로·없음 → SQLite 모드
  - `python scripts/download_db.py` 실행 시 `.env`의 `DATABASE_URL`이 로컬 절대경로로 자동 전환됨
- **LLM**: `cfg.SONNET_MODEL` (추천 카드) / `cfg.HAIKU_MODEL` (일반 카드) — `.env`에서 override 가능
- **외부 API**: Kakao REST (주소 → 좌표), ODsay (대중교통, 다중 키)
- **배포**: Vercel (서버리스, 60초 타임아웃) + Supabase pgBouncer 6543

## 프로젝트 구조

```
app/           # FastAPI 백엔드
api/           # Vercel 서버리스 진입점 (api/index.py)
web/           # 프론트엔드 (HTML/JS/CSS)
scripts/       # 데이터 파이프라인 + DB 마이그레이션
config.py      # 중앙 환경변수 관리 (cfg.*)
```

## 환경 변수

```bash
# DB 모드 — 형식으로 자동 분기
DATABASE_URL=postgresql://...      # Supabase 모드
DATABASE_URL=/abs/path/apt.db      # SQLite 모드 (download_db.py가 자동 설정)

# 런타임 필수
KAKAO_REST_API_KEY=...
ODSAY_KEY_1=..., ODSAY_REFERER_1=...   # 최대 20개 키
ANTHROPIC_API_KEY=...

# 모델명 override (기본값은 config.py 참조)
CLAUDE_SONNET_MODEL=...
CLAUDE_HAIKU_MODEL=...

# 스크립트 전용
VWORLD_API_KEY=..., MOLIT_API_KEY=...
```

## 코딩 규칙

### 설정·시크릿
- **`os.getenv()` 직접 호출 금지** — `from config import cfg` 후 `cfg.속성명` 사용
- **API 키·URL·모델명·숫자 상수 하드코딩 금지** — `config.py`에 추가 후 `cfg.*` 참조
- **`.env`는 절대 git에 올리지 않는다**

### DB 연결
- **`psycopg.connect()` / `sqlite3.connect()` 직접 호출 금지** — `from app.db import connect` 사용
- SQL 값 삽입은 f-string 금지, 반드시 `?` 파라미터 바인딩 사용

```python
# ❌ conn.execute(f"SELECT * FROM t WHERE col = {value}")
# ✅ conn.execute("SELECT * FROM t WHERE col = ?", (value,))
```

### 새 기능 체크리스트
- [ ] 새 설정값 → `config.py`에 `_optional()` / `_optional_int()` 추가
- [ ] 새 환경변수 → `CLAUDE.md` 환경 변수 섹션 업데이트
- [ ] Postgres 전용 SQL 문법 금지 → `app/portable.py` 헬퍼 활용

## 알려진 제약사항

| 제약 | 대응 |
|---|---|
| Vercel 60초 타임아웃 | `partial=true` → 재검색 시 캐시 자동 채움 |
| pgBouncer Transaction mode | `prepare_threshold=None` 자동 설정 |
| Vercel 파일시스템 read-only | `IS_SERVERLESS` 감지 후 로컬 저장 스킵 |
| Claude Haiku rate limit | 동시 호출 8개 이하 제한 |

## 로컬 개발 실행

```bash
pip install -r requirements.txt
python config.py                          # 환경변수 검증
uvicorn app.main:app --reload --port 8000
```

검증: `python -m pytest` / `python -m mypy app/` / `python -m flake8 app/`

## 의사소통 언어

한국어 기본. 커밋 메시지는 한국어·영어 모두 가능.

## 작업 일지 (Worklog)

`docs/worklog/<이름>_<YYYY-MM-DD>.md` 에 쌓인다. (`.author`, `.raw/`는 gitignore)

### 세션 시작 — `.author` 없을 때만 온보딩

1. 이름 제안 (1순위: 세션 이메일 앞부분 → 2순위: git config → 3순위: OS 사용자명)
   - 예: "이 작업을 **`chck0527`** 이름으로 기록할게요. 이대로 할까요?"
2. `docs/worklog/.author` 에 이름 저장.
3. DB 다운로드 제안:
   - `DATABASE_URL`이 `postgresql://` + `data/apartment.db` **없음** → `python scripts/download_db.py` 제안
   - `DATABASE_URL`이 `postgresql://` + **파일 있음** → `--compare-only` → 불일치 시 `--force` 제안
   - 파일 경로·없음 → 건너뜀

`.author` 있으면 온보딩 생략. 첫 응답에 `📝 작업 일지: <이름>님 작업으로 기록 중` 한 줄만 표시.

### 커밋 요청 시

`git diff` 확인 후 `docs/worklog/<이름>_<YYYY-MM-DD>.md` 맨 위에 추가:

```markdown
## <YYYY-MM-DD HH:MM> — (작업 제목)
**의도:** ...
**최종 상태:** ...
**건드린 파일·함수:** ...
**결정 / 버린 대안:** ...
**DB 변경:** (없으면 "없음". 스키마 변경은 scripts/*.sql 파일명 기록)
**함정·깨진 것:** ...
**미완성/TODO:** ...
```

> 스키마 변경 → `scripts/*.sql` 파일로 git에 남길 것.
