# Vercel + Supabase 배포 가이드

`real_estate` 앱을 Vercel Hobby 플랜에 올리는 방법.

---

## 아키텍처

```
브라우저 ──► Vercel CDN  (정적: web/*.html, /static/*)
            └─► Vercel Python 함수 (api/index.py → FastAPI app/main.py)
                  ├─► Supabase Postgres (모든 DB 읽기·쓰기)
                  ├─► Kakao REST  (주소 검색)
                  ├─► ODsay       (대중교통 길찾기)
                  └─► Anthropic   (LLM 친구 한 마디)
```

핵심 변경점:
- **DB**: 로컬 SQLite(144MB) → Supabase Postgres (런타임)
- **파일 쓰기**: ODsay raw JSON 아카이브 / wp 폴더 — Vercel에선 자동 스킵 (read-only FS)
- **ngrok 미들웨어 제거**, **정적 파일은 CDN이 직접 서빙**
- 로컬은 그대로 SQLite로 동작 (`DATABASE_URL` 미설정 시)

---

## 1단계: Supabase 프로젝트 생성 + 스키마

1. https://supabase.com 가입 → New project (Free tier OK, 500MB 제한)
2. Project Settings → Database → Connection string 복사:
   - **Direct connection (5432)** — 로컬 마이그레이션용
   - **Connection pooling: Transaction (6543)** — Vercel 함수용
3. **SQL Editor** 열고 `scripts/supabase_schema.sql` 전체 붙여넣어 Run
   - 모든 테이블·인덱스가 생성됨

---

## 2단계: 로컬 데이터 → Supabase 이관

```powershell
# .env 에 일단 5432 Direct connection 으로 DATABASE_URL 세팅
# (대량 INSERT는 pgBouncer가 끊을 수 있어서 Direct 권장)

pip install "psycopg[binary]" python-dotenv

# 전체 이관 (수십 분 소요 — trade_history가 가장 큼)
python scripts/migrate_sqlite_to_supabase.py

# 특정 테이블만
python scripts/migrate_sqlite_to_supabase.py --only=workplaces,apartments

# 다시 돌리려면 (TRUNCATE 후 재이관)
python scripts/migrate_sqlite_to_supabase.py --truncate
```

이관 끝나면 Supabase 대시보드 → Table Editor에서 행 수 확인.

---

## 3단계: Vercel 프로젝트 생성

```powershell
# Vercel CLI (없으면)
npm i -g vercel

# 프로젝트 루트에서
vercel login
vercel link        # 새 프로젝트 생성 또는 기존에 연결
```

또는 https://vercel.com 에서 GitHub 리포 import.

---

## 4단계: Environment Variables 등록

Vercel Dashboard → 프로젝트 → **Settings → Environment Variables**.
다음 키를 **Production / Preview / Development 모두 체크**하여 추가:

| Key | 값 | 비고 |
|---|---|---|
| `DATABASE_URL` | `postgresql://postgres.[REF]:[PWD]@aws-0-[REGION].pooler.supabase.com:6543/postgres` | **Transaction mode (6543) 필수** |
| `KAKAO_REST_API_KEY` | `xxxxxxxxxxxx` | developers.kakao.com |
| `KAKAO_JS_KEY` | `xxxxxxxxxxxx` | 프론트 지도 표시용 (선택) |
| `ODSAY_KEY_1` | `xxxxxxxxxxxx` | lab.odsay.com |
| `ODSAY_REFERER_1` | (도메인 등록 시 일치값) | 빈 문자열도 OK |
| `ODSAY_KEY_2` | (있으면 추가) | 호출 분산용 |
| `ODSAY_REFERER_2` | | |
| `ANTHROPIC_API_KEY` | `sk-ant-...` | console.anthropic.com |

다음 키는 **Vercel에 등록하지 마세요** — 데이터 파이프라인(`scripts/`) 전용:
- `VWORLD_API_KEY`, `MOLIT_API_KEY`, `KAKAO_NATIVE_KEY`, `DB_PATH`

`VERCEL=1`은 Vercel이 자동 세팅해주는 환경변수라 직접 추가 X.

---

## 5단계: 배포

```powershell
vercel --prod
```

또는 GitHub에 push (Vercel이 자동 빌드).

배포 끝나면:
- `https://<your-project>.vercel.app/`            → 랜딩 페이지 (web/index.html)
- `https://<your-project>.vercel.app/health`      → `{"status":"ok","backend":"supabase"}`
- `https://<your-project>.vercel.app/api/search`  → POST 검색 API

---

## Hobby 플랜 주의사항

| 제약 | 영향 | 대응 |
|---|---|---|
| 함수 타임아웃 60초 (vercel.json maxDuration) | ODsay 대량 호출 + LLM 코멘트 생성이 길어지면 잘림 | `_generate_comments_bg`는 응답 후 백그라운드 — Hobby에선 함수 종료와 함께 죽을 수 있음. 캐시 미스가 많은 초기 검색은 일부 코멘트만 들어옴. 재검색하면 채워짐 |
| 함수 사이즈 250MB | psycopg+anthropic+fastapi 합쳐 ~50MB → 여유 충분 | `.vercelignore`로 data/, scripts/, ngrok.exe 등 제외 |
| 파일시스템 read-only | `data/raw/odsay/.../cells/*.json` 저장 불가 | `IS_SERVERLESS` 가드로 자동 스킵 — DB의 transit_cache/routes만 채워짐 |
| Supabase Free 500MB | trade_history 큰 편 (3년치) | 부족하면 trade_history만 1년치로 축소하거나 Pro(8GB)로 |

---

## 로컬에서 Supabase 모드로 테스트

```powershell
# .env 에 DATABASE_URL 추가 후
uvicorn app.main:app --reload --port 8000

# /health 로 backend 확인
# {"status":"ok","backend":"supabase"}
```

`DATABASE_URL` 빼면 다시 로컬 SQLite로 돌아갑니다.

---

## 트러블슈팅

- **`prepared statement "..." already exists`**
  → pgBouncer 6543 Transaction mode인데 prepared statement가 켜진 상태.
  `app/db.py`는 `prepare_threshold=None` 자동 설정 — 이 에러 뜨면 Direct(5432)로 잘못 연결한 것.

- **`function timeout`**
  → ODsay 캐시 미스가 많은 새 직장 주소 첫 검색. 60초 한도 내 못 끝낸 셀은 transit_cache에 안 들어가서 다음 검색에서 재시도됨.

- **함수 사이즈 초과**
  → `.vercelignore` 점검. `data/`, `scripts/`, `ngrok.exe`가 빠져 있는지.

- **CORS / 정적 파일 404**
  → vercel.json `outputDirectory: "web"` 그대로 두면 `web/` 안의 파일이 CDN 루트에서 서빙됨. `web/static/*` → `https://.../static/*` 로 자동 매핑.

- **Korean 컬럼 (`step1_노선`) 쿼리 오류**
  → Postgres는 quoted identifier가 필요. 런타임 코드는 컬럼 직접 호출 안 하고 `r['step1_노선']` row 접근만 해서 문제 없음. 직접 SQL 작성 시엔 `"step1_노선"` 큰따옴표.
