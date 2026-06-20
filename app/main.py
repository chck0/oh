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
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from config import cfg
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
    # Windows 콘솔(cp949)에서 한글/em-dash 출력 시 UnicodeEncodeError 방지.
    # errors='backslashreplace'로 어떤 문자도 print가 죽지 않게 보장.
    sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace', line_buffering=True)  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding='utf-8', errors='backslashreplace', line_buffering=True)  # type: ignore[union-attr]
except Exception:
    pass


# ── 모듈 import 단계에서 죽으면 Vercel은 함수가 아예 시작 안 됨 →
#    config / app 모듈을 try로 감싸 어디서 죽었는지 로그에 남기고
#    그래도 FastAPI 객체는 만들어서 /api/_debug 만이라도 응답하게 함.
_IMPORT_ERROR: str | None = None
try:
    log.info('importing app modules...')
    from app.search import router as search_router
    from app.db import connect as db_connect
    log.info('app modules imported OK (backend=%s)',
             'supabase' if cfg.USE_PG else 'sqlite')
except Exception as e:
    _IMPORT_ERROR = f'{type(e).__name__}: {e}\n{traceback.format_exc()}'
    log.error('IMPORT FAILED: %s', _IMPORT_ERROR)
    search_router = None  # type: ignore[assignment]
    db_connect = None     # type: ignore[assignment]


@asynccontextmanager
async def _lifespan(app: FastAPI):
    import asyncio as _asyncio
    log.info('=== startup === VERCEL=%s DEBUG_API=%s', cfg.IS_SERVERLESS, DEBUG_API)
    if _IMPORT_ERROR:
        log.error('startup skipped because import failed')
    elif db_connect is not None:
        if not cfg.USE_PG:
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
                            model     TEXT DEFAULT 'claude-haiku-4-5-20251001',
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
                            model        TEXT DEFAULT 'claude-haiku-4-5-20251001',
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
        else:
            # Postgres 모드: camelCase 컬럼 목록을 information_schema에서 동적 로드
            # → 스키마 변경(컬럼 추가 등)에 코드 수정 없이 자동 대응
            try:
                from app.db import refresh_camel_cols
                conn = db_connect()
                try:
                    refresh_camel_cols(conn)
                finally:
                    conn.close()
            except Exception as e:
                log.warning('camelCase 컬럼 로드 실패 (non-fatal, fallback 사용): %s', e)

        # ── 백그라운드 캐시 워밍업 (Supabase cold start 대응) ──────
        # 서버 시작 직후 비동기로 메모리 캐시를 미리 채워둠
        # → 첫 사용자 요청도 캐시 히트로 응답
        async def _warm_caches():
            try:
                t0 = time.time()
                from app.search import _get_cached_apts
                from app.workplaces import _wp_mem_cache
                from app.portable import list_columns
                conn = db_connect()
                # 1) apartments 전체 로드
                apts = _get_cached_apts(conn)
                log.info('cache warm: %d apts loaded (%.0fms)', len(apts), (time.time()-t0)*1000)
                # 2) workplaces 전체를 인메모리 캐시에
                from app.portable import list_columns as _lc
                cols = _lc(conn, 'workplaces')
                rows = conn.execute('SELECT * FROM workplaces').fetchall()
                for row in rows:
                    d = dict(zip(cols, [row[c] for c in cols]))
                    _wp_mem_cache[d['address_input']] = d
                log.info('cache warm: %d workplaces loaded (%.0fms)', len(rows), (time.time()-t0)*1000)
                conn.close()
            except Exception as e:
                log.warning('cache warm failed (non-fatal): %s', e)

        # 테스트 환경에서는 워밍을 끈다(BADUGI_NO_WARM): 이 태스크가 라우팅 안 된
        # 실 db_connect()로 모듈 캐시(_apt_cache/_wp_mem_cache)를 채워, conftest의
        # 캐시 리셋 직후 요청 처리 중 비동기로 재오염시키는 레이스를 유발한다.
        if not os.getenv('BADUGI_NO_WARM'):
            _asyncio.create_task(_warm_caches())

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
    except HTTPException:
        raise
    except Exception as e:
        tb = traceback.format_exc()
        dt = int((time.time() - t0) * 1000)
        log.error('!!! %s %s after %dms: %s\n%s', method, path, dt, e, tb)
        payload: dict = {
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
if cfg.IS_SERVERLESS and not _raw_origins.strip():
    log.warning('ALLOWED_ORIGINS 미설정 — localhost fallback이 production에 적용 중. Vercel 대시보드에서 설정 필요')
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
        "backend": "supabase" if cfg.USE_PG else "sqlite",
        "import_error": _IMPORT_ERROR,
    }


# ── 진단 엔드포인트 — 환경/DB/외부API 상태 한 번에 확인 ──────
@app.get("/api/_debug")
def debug_status():
    """문제 진단용. DEBUG_API=1 일 때만 응답 (운영 시 비활성)."""
    if not DEBUG_API:
        return JSONResponse({'error': 'debug disabled'}, status_code=404)

    report = {
        'serverless': cfg.IS_SERVERLESS,
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
        import urllib.request
        import urllib.parse
        import json
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
        from app.transit import ODSAY_URL as _ODSAY_URL
        url = _ODSAY_URL + '?' + urllib.parse.urlencode(params)
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
            err = j.get('error')
            err_code = err.get('code') if isinstance(err, dict) else None
            err_msg  = err.get('message') if isinstance(err, dict) else None
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
        import urllib.request
        import urllib.parse
    except Exception as e:
        return {'error': f'{type(e).__name__}: {e}'}
    params = urllib.parse.urlencode({'query': '서울 강남구 테헤란로 504'})
    from app.workplaces import KAKAO_URL as _KAKAO_URL
    req = urllib.request.Request(
        f'{_KAKAO_URL}?{params}',
        headers={'Authorization': f'KakaoAK {cfg.KAKAO_REST_API_KEY}'},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return {'http_status': r.status, 'body_excerpt': r.read().decode('utf-8')[:300]}
    except urllib.error.HTTPError as e:
        return {'http_status': e.code, 'body_excerpt': e.read().decode('utf-8')[:300]}
    except Exception as e:
        return {'error': f'{type(e).__name__}: {e}'}


# ── 최근 검색 직장 히스토리 (spec-15) ───────────────────────
@app.get("/api/workplaces/recent")
def workplaces_recent(limit: int = 5):
    """최근 검색한 직장 목록 (search_count DESC, last_used DESC).

    search.html 히스토리 칩 용도. limit 1~10 클램프.
    """
    limit = max(1, min(limit, 10))
    try:
        from app.db import connect as db_connect  # lazy — 시작 시 import 불필요
        conn = db_connect()
        rows = conn.execute(
            'SELECT address_input, address_norm, search_count, last_used '
            'FROM workplaces '
            'WHERE address_norm IS NOT NULL AND address_input IS NOT NULL '
            'ORDER BY last_used DESC, search_count DESC '
            'LIMIT ?',
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        log.warning('workplaces/recent error: %s', e)
        return []


# ── 카카오맵 SDK 로더 (JS 키 환경변수화) ─────────────────────
# 프론트엔드 HTML이 JS 키를 하드코딩하지 않도록 백엔드가 SDK 로더 JS를 내려줌.
# 키는 .env의 KAKAO_JS_KEY에서 읽음.
#
# [왜 302 리다이렉트가 아니라 document.write인가]
# 카카오 SDK(sdk.js)는 자신의 <script> 태그 src에서 libraries(services 등)를 파싱한다.
# 302로 리다이렉트하면 DOM의 태그 src는 프록시 URL(/api/kakao-sdk?...)로 남아
# 카카오가 sdk.js 태그를 못 찾아 libraries를 못 읽는다 → kakao.maps.services 미로드.
# 따라서 실제 dapi URL을 가진 <script>를 직접 써넣어 카카오가 libraries를 인식하게 한다.
# 파싱 중(head)에는 document.write가 동기 로드라 기존 호출부(kakao.maps.load) 호환.
@app.get("/api/kakao-sdk")
def kakao_sdk_loader(libraries: str = ""):
    from fastapi.responses import Response
    if not cfg.KAKAO_JS_KEY:
        return JSONResponse({'error': 'KAKAO_JS_KEY not configured'}, status_code=500)
    src = f"https://dapi.kakao.com/v2/maps/sdk.js?appkey={cfg.KAKAO_JS_KEY}&autoload=false"
    if libraries:
        src += f"&libraries={libraries}"
    js = (
        "(function(){var u='" + src + "';"
        "if(document.readyState==='loading'){"
        "document.write('<script src=\"'+u+'\"><\\/script>');"
        "}else{var s=document.createElement('script');s.src=u;document.head.appendChild(s);}"
        "})();"
    )
    return Response(content=js, media_type="application/javascript")


# ── API 라우터 ───────────────────────────────────────────────
if search_router is not None:
    app.include_router(search_router, prefix="/api")


# ── 정적 프론트엔드 (/web/*) ─────────────────────────────────
# Vercel에서는 vercel.json의 rewrites가 /web/* 를 CDN에서 직접 서빙.
# FastAPI 마운트는 로컬 dev 전용.
if not cfg.IS_SERVERLESS:
    WEB_DIR = Path(__file__).parent.parent / 'web'
    if WEB_DIR.exists():
        app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
