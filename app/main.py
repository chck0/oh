"""
FastAPI 진입점

로컬:    uvicorn app.main:app --reload --port 8000
Vercel:  api/index.py 가 이 app을 import해서 서빙
"""
import os
import sys
import time
import logging
import traceback
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

IS_SERVERLESS = bool(os.getenv('VERCEL'))
# DEBUG_API=1 로 켜면 /api/_debug 노출 + 500 응답에 traceback 포함
# 운영 안정화되면 Vercel에서 이 env var 제거하면 됨
DEBUG_API = os.getenv('DEBUG_API', '1') == '1'

# ── 로깅 ─────────────────────────────────────────────────────
# Vercel은 stdout/stderr를 Runtime Logs로 캡쳐. force=True로 기존 핸들러 덮어쓰기
# (FastAPI/uvicorn이 먼저 basicConfig를 호출했을 수 있음)
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s',
    datefmt='%H:%M:%S',
    stream=sys.stdout,
    force=True,
)
log = logging.getLogger('app')

# Python stdout 버퍼링 해제 (Vercel은 자동 unbuffered지만 한 번 더 보장)
try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass


# ── 모듈 import 단계에서 죽으면 Vercel은 함수가 아예 시작 안 됨 →
#    config / app 모듈을 try로 감싸 어디서 죽었는지 로그에 남기고
#    그래도 FastAPI 객체는 만들어서 /api/_debug 만이라도 응답하게 함.
_IMPORT_ERROR: str | None = None
try:
    log.info('importing app modules...')
    from app.search import router as search_router
    from app.db import connect as db_connect, USE_PG
    from config import cfg  # noqa: F401  (env validation)
    log.info('app modules imported OK (backend=%s)',
             'supabase' if USE_PG else 'sqlite')
except Exception as e:
    _IMPORT_ERROR = f'{type(e).__name__}: {e}\n{traceback.format_exc()}'
    log.error('IMPORT FAILED: %s', _IMPORT_ERROR)
    USE_PG = False
    search_router = None
    db_connect = None


app = FastAPI(title="real_estate", version="0.1.0")


# ── 모든 요청/응답 로깅 + 예외 캐치 ─────────────────────────
@app.middleware("http")
async def _log_and_catch(request: Request, call_next):
    t0 = time.time()
    method, path = request.method, request.url.path
    log.info('--> %s %s', method, path)
    try:
        resp = await call_next(request)
        dt = int((time.time() - t0) * 1000)
        log.info('<-- %s %s [%d] %dms', method, path, resp.status_code, dt)
        return resp
    except Exception as e:
        tb = traceback.format_exc()
        dt = int((time.time() - t0) * 1000)
        log.error('!!! %s %s after %dms: %s\n%s', method, path, dt, e, tb)
        payload = {
            'error': f'{type(e).__name__}: {e}',
            'path': path,
            'method': method,
        }
        if DEBUG_API:
            payload['traceback'] = tb.splitlines()
        return JSONResponse(payload, status_code=500)


# ── 앱 시작 시 환경 + DB 점검 ────────────────────────────────
@app.on_event("startup")
def _startup():
    log.info('=== startup === VERCEL=%s DEBUG_API=%s', IS_SERVERLESS, DEBUG_API)
    if _IMPORT_ERROR:
        log.error('startup skipped because import failed')
        return

    # SQLite(로컬)에서만 신규 테이블 자동 생성
    if not USE_PG and db_connect is not None:
        try:
            conn = db_connect()
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS apt_friend_comment (
                        apt_seq   TEXT NOT NULL,
                        wp_id     INTEGER NOT NULL,
                        tier      TEXT NOT NULL,
                        comment   TEXT NOT NULL,
                        model     TEXT DEFAULT 'claude-haiku-4-5',
                        created_at TEXT DEFAULT (datetime('now','localtime')),
                        PRIMARY KEY (apt_seq, wp_id)
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS apt_pt_friend_comment (
                        apt_seq      TEXT NOT NULL,
                        pyeong_type  TEXT NOT NULL,
                        wp_id        INTEGER NOT NULL,
                        comment      TEXT NOT NULL,
                        model        TEXT DEFAULT 'claude-haiku-4-5',
                        created_at   TEXT DEFAULT (datetime('now','localtime')),
                        PRIMARY KEY (apt_seq, pyeong_type, wp_id)
                    )
                """)
                conn.commit()
            finally:
                conn.close()
            log.info('local sqlite schema ensured')
        except Exception as e:
            log.error('sqlite schema ensure failed: %s', e)


# ── CORS ─────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 헬스체크 ─────────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "status": "ok" if not _IMPORT_ERROR else "import_failed",
        "backend": "supabase" if USE_PG else "sqlite",
        "import_error": _IMPORT_ERROR,
    }


# ── 진단 엔드포인트 — 환경/DB/외부API 상태 한 번에 확인 ──────
@app.get("/api/_debug")
def debug_status():
    """문제 진단용. DEBUG_API=1 일 때만 응답 (운영 시 비활성)."""
    if not DEBUG_API:
        return JSONResponse({'error': 'debug disabled'}, status_code=404)

    report = {
        'serverless': IS_SERVERLESS,
        'import_error': _IMPORT_ERROR,
        'env': {},
        'db': {},
    }
    # 환경변수 존재 여부 (값은 마스킹)
    for k in ['DATABASE_URL', 'KAKAO_REST_API_KEY', 'KAKAO_JS_KEY',
              'ANTHROPIC_API_KEY', 'ODSAY_KEY_1', 'ODSAY_REFERER_1',
              'ODSAY_KEY_2', 'ODSAY_REFERER_2', 'VERCEL', 'DEBUG_API']:
        v = os.getenv(k)
        if v is None:
            report['env'][k] = None
        elif k in ('VERCEL', 'DEBUG_API', 'ODSAY_REFERER_1', 'ODSAY_REFERER_2'):
            report['env'][k] = v
        else:
            report['env'][k] = f'<set:{len(v)}chars>'

    # DB 연결 + 테이블별 행 수
    if _IMPORT_ERROR or db_connect is None:
        report['db']['status'] = 'unavailable (import failed)'
        return report

    try:
        t0 = time.time()
        conn = db_connect()
        report['db']['connect_ms'] = int((time.time() - t0) * 1000)
        try:
            counts = {}
            for t in ['workplaces', 'apartments', 'kapt_complexes',
                      'trade_recent', 'trade_history', 'apt_walking_poi',
                      'transit_cache', 'transit_routes',
                      'apt_pt_friend_comment']:
                try:
                    n = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
                    counts[t] = n
                except Exception as e:
                    counts[t] = f'ERR: {type(e).__name__}: {e}'
            report['db']['counts'] = counts
            report['db']['status'] = 'ok'
        finally:
            conn.close()
    except Exception as e:
        report['db']['status'] = f'ERR: {type(e).__name__}: {e}'
        report['db']['traceback'] = traceback.format_exc().splitlines()

    return report


# ── API 라우터 ───────────────────────────────────────────────
if search_router is not None:
    app.include_router(search_router, prefix="/api")


# ── 정적 프론트엔드 (/web/*) ─────────────────────────────────
# Vercel에서는 vercel.json의 rewrites가 /web/* 를 CDN에서 직접 서빙.
# FastAPI 마운트는 로컬 dev 전용.
if not IS_SERVERLESS:
    WEB_DIR = Path(__file__).parent.parent / 'web'
    if WEB_DIR.exists():
        app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
