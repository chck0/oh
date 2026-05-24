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

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

IS_SERVERLESS = bool(os.getenv('VERCEL'))
# DEBUG_API=1 로 켜면 /api/_debug 노출 + 500 응답에 traceback 포함
# 운영 안정화되면 Vercel에서 이 env var 제거하면 됨
DEBUG_API = os.getenv('DEBUG_API', '0') == '1'

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


@asynccontextmanager
async def _lifespan(app: FastAPI):
    log.info('=== startup === VERCEL=%s DEBUG_API=%s', IS_SERVERLESS, DEBUG_API)
    if _IMPORT_ERROR:
        log.error('startup skipped because import failed')
    elif not USE_PG and db_connect is not None:
        # SQLite(로컬)에서만 신규 테이블 자동 생성
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
    yield


app = FastAPI(title="real_estate", version="0.1.0", lifespan=_lifespan)


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


# ── CORS ─────────────────────────────────────────────────────
# 운영: Vercel 환경변수 ALLOWED_ORIGINS 에 쉼표 구분 도메인 등록
# 예: https://badugi.vercel.app,https://badugi-preview.vercel.app
# 미설정 시 로컬 dev 전용으로 localhost만 허용
_raw_origins = os.getenv('ALLOWED_ORIGINS', '')
ALLOWED_ORIGINS: list[str] = (
    [o.strip() for o in _raw_origins.split(',') if o.strip()]
    or ['http://localhost:8000', 'http://localhost:3000', 'http://127.0.0.1:8000']
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
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


# ── ODsay 키 직접 테스트 ────────────────────────────────────
@app.get("/api/_test_odsay")
def test_odsay():
    """등록한 ODsay 키 각각에 실제 요청을 보내 응답을 그대로 반환.
    어떤 키/Referer 조합이 막혔는지 즉시 진단."""
    if not DEBUG_API:
        return JSONResponse({'error': 'debug disabled'}, status_code=404)
    try:
        from config import cfg
        import urllib.request, urllib.parse, json
    except Exception as e:
        return {'error': f'{type(e).__name__}: {e}'}

    # 동작구청 → 강남역 (서울 안 흔한 경로)
    base_params = {
        'SX': '126.9395', 'SY': '37.5124',
        'EX': '127.0276', 'EY': '37.4979',
        'lang': '0', 'OPT': '0',
    }

    results = []
    for i, k in enumerate(cfg.ODSAY_KEYS, 1):
        params = {**base_params, 'apiKey': k['key']}
        url = 'https://api.odsay.com/v1/api/searchPubTransPathT?' + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={'Referer': k['referer'] or ''})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                body = r.read().decode('utf-8')
                status = r.status
        except Exception as e:
            body = str(e)
            status = -1
        # body 너무 길면 자름 + error 키만 있는지 확인
        try:
            j = json.loads(body)
            has_result = 'result' in j
            err_code = j.get('error', {}).get('code') if isinstance(j.get('error'), dict) else None
            err_msg  = j.get('error', {}).get('message') if isinstance(j.get('error'), dict) else None
        except Exception:
            has_result = False
            err_code = err_msg = None
        results.append({
            'key_index': i,
            'key_prefix': k['key'][:8] + '...',
            'referer_sent': k['referer'] or '(empty)',
            'http_status': status,
            'has_result': has_result,
            'error_code': err_code,
            'error_msg':  err_msg,
            'body_excerpt': body[:400],
        })
    return {'results': results}


# ── Kakao 키 직접 테스트 ────────────────────────────────────
@app.get("/api/_test_kakao")
def test_kakao():
    """Kakao REST 키로 주소검색 1회 호출. 200/401/403 등으로 즉시 판별."""
    if not DEBUG_API:
        return JSONResponse({'error': 'debug disabled'}, status_code=404)
    try:
        from config import cfg
        import urllib.request, urllib.parse
    except Exception as e:
        return {'error': f'{type(e).__name__}: {e}'}
    params = urllib.parse.urlencode({'query': '서울 강남구 테헤란로 504'})
    req = urllib.request.Request(
        f'https://dapi.kakao.com/v2/local/search/address.json?{params}',
        headers={'Authorization': f'KakaoAK {cfg.KAKAO_REST_API_KEY}'},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return {'http_status': r.status, 'body_excerpt': r.read().decode('utf-8')[:300]}
    except urllib.error.HTTPError as e:
        return {'http_status': e.code, 'body_excerpt': e.read().decode('utf-8')[:300]}
    except Exception as e:
        return {'error': f'{type(e).__name__}: {e}'}


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
