"""
ODsay 호출 + transit_cache/routes 적재
(sandbox/51, 52 통합 → production용)

Vercel(서버리스)에서는 raw JSON 아카이브 쓰기를 자동 스킵 (IS_SERVERLESS).
"""
import asyncio
import aiohttp
import json
import time
import math
import logging
from config import cfg
from app.workplaces import raw_dir
from app.portable import upsert_sql

# 모듈 레벨 re-export — 테스트에서 monkeypatch.setattr(transit_mod, 'IS_SERVERLESS', ...)로
# 교체할 수 있도록 모듈 속성으로 노출. 값은 cfg에서 가져옴.
IS_SERVERLESS = cfg.IS_SERVERLESS
log = logging.getLogger('app.transit')

GRID                = 0.0045
ODSAY_URL           = "https://api.odsay.com/v1/api/searchPubTransPathT"
# 실측(scripts/bench_odsay_sleep.py) 기반 권장값:
#   1키 단독 한도 = 동시 1, 동시 2면 sleep 300ms 필요해야 100% 성공.
#   7키 분산 시 동시 2 + sleep 200ms = 99.3% 성공, 19.8 RPS.
# 이전 4/100ms는 실측 시 83% 실패 → 검색 결과 손실 + 캐시 오염.
PER_KEY_CONCURRENCY = 2
ROUND_SLEEP_MS      = 200
HTTP_TIMEOUT        = 15
# 429 백오프: ODsay는 1초만 쉬면 즉시 복구됨(실측). 1회만 재시도.
RETRY_BACKOFF_S     = 1.0

ALLOWED_COMBOS    = {(0,1),(0,2),(1,0),(2,0),(1,1)}
WALK_ONLY_MAX_MIN = 15
FIRST_LAST_WALK_M = 840
TRANSFER_WALK_M   = 420

KEYS = [{'owner': f'key{i+1}', **k} for i, k in enumerate(cfg.ODSAY_KEYS)]

# ── transit_routes 컬럼 구조 ─────────────────────────────────
# step이 추가될 때는 MAX_STEPS 숫자만 바꾸면 INSERT/SELECT 자동 반영.
MAX_STEPS = 5
_STEP_FIELDS = ('type', 'time_min', 'dist_m', '노선', '출발', '도착', 'linestring')
_ROUTE_BASE_COLS = ['origin_cell', 'wp_id', 'rank',
                    'total_time_min', 'bus_cnt', 'subway_cnt']
_ROUTE_STEP_COLS = [f'step{n}_{f}' for n in range(1, MAX_STEPS + 1)
                    for f in _STEP_FIELDS]
_ROUTE_ALL_COLS  = _ROUTE_BASE_COLS + _ROUTE_STEP_COLS

_ROUTE_INSERT_SQL = (
    f'INSERT INTO transit_routes ({", ".join(_ROUTE_ALL_COLS)}) '
    f'VALUES ({", ".join(["?"] * len(_ROUTE_ALL_COLS))})'
)


# ── 좌표 유틸 ────────────────────────────────────────────────
def cell_of(lat, lng):
    return f"R{int(lat/GRID):05d}C{int(lng/GRID):05d}"


def cell_center(cell_code):
    return (int(cell_code[1:6]) + 0.5) * GRID, (int(cell_code[7:12]) + 0.5) * GRID


def haversine(lat1, lng1, lat2, lng2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlng/2)**2)
    return R * 2 * math.asin(math.sqrt(a))


# ── 경로 필터 + 랭킹 ──────────────────────────────────────────
def filter_path(p):
    info = p['info']
    bt = info['busTransitCount']
    st = info['subwayTransitCount']
    subs = p['subPath']
    if bt == 0 and st == 0:
        return info['totalTime'] <= WALK_ONLY_MAX_MIN
    if (bt, st) not in ALLOWED_COMBOS:
        return False
    if subs[0].get('distance', 0) > FIRST_LAST_WALK_M:
        return False
    if subs[-1].get('distance', 0) > FIRST_LAST_WALK_M:
        return False
    for sp in subs[1:-1]:
        if sp.get('trafficType') == 3 and sp.get('distance', 0) > TRANSFER_WALK_M:
            return False
    return True


def rank_paths(paths):
    valid = [p for p in paths if filter_path(p)]

    def pri(p):
        bt = p['info']['busTransitCount']
        st = p['info']['subwayTransitCount']
        cls = {(0,1):1,(1,1):2,(0,2):3,(1,0):4}.get((bt,st), 5)
        return (cls, p['info']['totalTime'])

    valid.sort(key=pri)
    return [(i+1, p) for i, p in enumerate(valid)]


def to_steps(subpath_list):
    steps = []
    for sp in subpath_list:
        tt = sp.get('trafficType')
        t = sp.get('sectionTime', 0)
        d = sp.get('distance', 0)
        if tt == 3:
            if d == 0:
                steps.append({'type':'환승도보','time':t,'dist':0,'line':'','from':'','to':'','linestring':None})
            else:
                # 도보: 시작·끝 좌표만 직선
                sx, sy = sp.get('startX'), sp.get('startY')
                ex, ey = sp.get('endX'), sp.get('endY')
                ls = f'{sx},{sy} {ex},{ey}' if sx and sy and ex and ey else None
                steps.append({'type':'도보','time':t,'dist':d,'line':'','from':'','to':'','linestring':ls})
        elif tt in (1, 2):
            lane = sp.get('lane', [{}])[0]
            # passStopList.stations 좌표 배열로 linestring 생성
            stations = sp.get('passStopList', {}).get('stations', [])
            if stations:
                ls = ' '.join(f"{s['x']},{s['y']}" for s in stations if s.get('x') and s.get('y'))
            else:
                # fallback: 시작·끝 좌표만
                sx, sy = sp.get('startX'), sp.get('startY')
                ex, ey = sp.get('endX'), sp.get('endY')
                ls = f'{sx},{sy} {ex},{ey}' if sx and sy and ex and ey else None
            if tt == 1:
                steps.append({'type':'지하철','time':t,'dist':d,
                              'line': lane.get('name',''),
                              'from': sp.get('startName',''), 'to': sp.get('endName',''),
                              'linestring': ls})
            else:
                steps.append({'type':'버스','time':t,'dist':d,
                              'line': lane.get('busNo',''),
                              'from': sp.get('startName',''), 'to': sp.get('endName',''),
                              'linestring': ls})
    return steps[:5]


def step_cols(steps, n):
    if n <= len(steps):
        s = steps[n-1]
        return s['type'], s['time'], s['dist'], s['line'], s['from'], s['to'], s.get('linestring')
    return '', None, None, '', '', '', None


# ── ODsay 호출 ───────────────────────────────────────────────
# 키별 동시성 제한을 보장하는 모듈 전역 세마포어.
# fetch_cells가 동시에 N개 호출돼도(예: dual workplace) 같은 키에 대해
# 동시 in-flight 호출 수는 PER_KEY_CONCURRENCY 이하로 유지된다.
# asyncio.Semaphore는 이벤트 루프 종속이라 lazy로 생성.
_KEY_SEMAPHORES: dict[str, asyncio.Semaphore] | None = None


def _get_key_sems() -> dict[str, asyncio.Semaphore]:
    global _KEY_SEMAPHORES
    if _KEY_SEMAPHORES is None:
        _KEY_SEMAPHORES = {k['owner']: asyncio.Semaphore(PER_KEY_CONCURRENCY)
                           for k in KEYS}
    return _KEY_SEMAPHORES


def _parse_err_msg(data) -> tuple[str, str]:
    """ODsay 에러 응답에서 (code, message) 추출. 없으면 ('', '')."""
    err = data.get('error')
    if isinstance(err, list) and err:
        err = err[0]
    if isinstance(err, dict):
        return str(err.get('code', '')), str(err.get('message', ''))
    return '', ''


async def _do_call(session, key_info, origin_cell, dest_lat, dest_lng):
    """단일 HTTP 호출 — 재시도/세마포어 없이 raw 응답만 돌려준다."""
    o_lat, o_lng = cell_center(origin_cell)
    params = {
        'apiKey': key_info['key'],
        'SX': o_lng, 'SY': o_lat, 'EX': dest_lng, 'EY': dest_lat,
        'lang': 0, 'OPT': 0,
    }
    headers = {'Referer': key_info['referer']}
    async with session.get(
        ODSAY_URL, params=params, headers=headers,
        timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT),
    ) as r:
        raw = await r.text()
        return raw, r.status


async def _call_one(session, key_info, sem, origin_cell, dest_lat, dest_lng):
    """
    한 셀에 대해 ODsay 호출 + 429 백오프 1회 재시도.

    반환 규칙 (세 번째 raw 필드가 캐시 여부 신호):
      - raw == ''   → 캐시 X (인증 실패, 429, 네트워크 예외 — 다음 검색 재시도)
      - raw != ''   → 캐시 O (정상 응답: 통근 가능 or 진짜 통근 불가)
    """
    for attempt in (0, 1):
        try:
            async with sem:
                raw, status = await _do_call(
                    session, key_info, origin_cell, dest_lat, dest_lng,
                )
            data = json.loads(raw)
            if 'result' in data:
                return origin_cell, rank_paths(data['result'].get('path', [])), raw

            code, err_msg = _parse_err_msg(data)
            is_429 = code == '429' or '429' in err_msg or 'Too Many' in err_msg
            is_auth_fail = ('ApiKeyAuthFailed' in err_msg
                            or 'apikey' in err_msg.lower())

            if is_429 and attempt == 0:
                # 다른 호출에 슬롯 양보하고 1초 쉰 뒤 재시도.
                await asyncio.sleep(RETRY_BACKOFF_S)
                continue

            log.warning(
                'ODsay no-result [%s] key=%s status=%d body=%s',
                origin_cell, key_info['owner'], status, raw[:300],
            )
            # 429 / 인증실패는 캐시 X(다음 검색에서 재시도). 그 외는 캐시 O.
            if is_429 or is_auth_fail:
                return origin_cell, [], ''
            return origin_cell, [], raw
        except Exception as e:
            log.error('ODsay exception [%s] key=%s attempt=%d: %s',
                      origin_cell, key_info['owner'], attempt, e)
            if attempt == 0:
                await asyncio.sleep(RETRY_BACKOFF_S)
                continue
            return origin_cell, [], ''
    return origin_cell, [], ''


async def fetch_cells(conn, wp_row, cells_to_fetch: list[str]) -> dict:
    """
    셀 리스트에 대해 ODsay 호출 + raw 저장 + transit_cache/routes INSERT.
    반환: { 'fetched': N, 'passed': M, 'failed': K, 'elapsed_ms': ... }
    """
    if not cells_to_fetch:
        return {'fetched': 0, 'passed': 0, 'failed': 0, 'elapsed_ms': 0}

    wp_id   = wp_row['wp_id']
    dest_lat = wp_row['lat']
    dest_lng = wp_row['lng']

    # 모듈 전역 세마포어 사용 → 동시에 여러 fetch_cells(예: dual workplace)가
    # 호출돼도 키별 동시 in-flight 호출 수가 PER_KEY_CONCURRENCY 이하로 유지됨.
    sems = _get_key_sems()
    ROUND_SIZE = len(KEYS) * PER_KEY_CONCURRENCY
    rounds = (len(cells_to_fetch) + ROUND_SIZE - 1) // ROUND_SIZE

    cells_dir = None
    if not IS_SERVERLESS:
        cells_dir = raw_dir(wp_row) / 'cells'
        cells_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    ok_cnt = fail_cnt = 0
    cache_inserts, route_inserts = [], []
    now = time.strftime('%Y-%m-%d %H:%M:%S')

    connector = aiohttp.TCPConnector(limit=30, ttl_dns_cache=300)
    async with aiohttp.ClientSession(connector=connector) as session:
        for ri in range(rounds):
            batch = cells_to_fetch[ri*ROUND_SIZE:(ri+1)*ROUND_SIZE]
            tasks = []
            for i, c in enumerate(batch):
                k = KEYS[i % len(KEYS)]
                tasks.append(_call_one(session, k, sems[k['owner']], c, dest_lat, dest_lng))
            results = await asyncio.gather(*tasks)

            for origin, ranked, raw in results:
                rel = None
                if cells_dir is not None and raw:
                    fpath = cells_dir / f'{origin}.json'
                    fpath.write_text(raw, encoding='utf-8')
                    rel = str(fpath.relative_to(cfg.PROJECT_ROOT)).replace('\\', '/')
                size = len(raw)

                if ranked:
                    rank1 = ranked[0][1]['info']
                    cache_inserts.append((
                        origin, wp_id,
                        rank1['totalTime'], rank1['busTransitCount'], rank1['subwayTransitCount'],
                        rank1.get('totalWalk', 0), 1, 0,  # path_idx 의미 없어짐, 0
                        rel, size, now
                    ))
                    for rank, p in ranked:
                        info = p['info']
                        steps = to_steps(p['subPath'])
                        step_data = [step_cols(steps, i) for i in range(1, MAX_STEPS + 1)]
                        route_inserts.append((
                            origin, wp_id, rank,
                            info['totalTime'], info['busTransitCount'], info['subwayTransitCount'],
                            *(v for s in step_data for v in s),
                        ))
                    ok_cnt += 1
                else:
                    cache_inserts.append((
                        origin, wp_id, None, None, None, None, 0, -1,
                        rel, size, now
                    ))
                    fail_cnt += 1

            if ri < rounds - 1:
                await asyncio.sleep(ROUND_SLEEP_MS / 1000)

    # ── INSERT (이 wp의 기존 routes는 이미 있을 수 있으니 origin_cell 단위로 교체) ──
    if route_inserts:
        # 동일 (origin_cell, wp_id)의 기존 행 삭제 (rank 재계산 위해) — 단일 쿼리
        # 같은 호출 내 route_inserts는 모두 동일 wp_id이므로 origin_cell IN (?) 로 처리
        origin_cells = list(set(r[0] for r in route_inserts))
        ph = ','.join(['?'] * len(origin_cells))
        conn.execute(
            f'DELETE FROM transit_routes WHERE wp_id=? AND origin_cell IN ({ph})',
            [wp_id] + origin_cells,
        )

    conn.executemany(
        upsert_sql(
            'transit_cache',
            ['origin_cell', 'wp_id', 'total_time', 'bus_cnt', 'subway_cnt',
             'walk_total', 'passed_filter', 'path_idx', 'raw_file',
             'response_size', 'fetched_at'],
            pk_cols=['origin_cell', 'wp_id'],
        ),
        cache_inserts,
    )

    conn.executemany(_ROUTE_INSERT_SQL, route_inserts)

    # workplaces.cells_cached 갱신
    cached = conn.execute(
        'SELECT COUNT(*) FROM transit_cache WHERE wp_id=? AND passed_filter=1', (wp_id,)
    ).fetchone()[0]
    conn.execute('UPDATE workplaces SET cells_cached=? WHERE wp_id=?', (cached, wp_id))
    conn.commit()

    return {
        'fetched': ok_cnt + fail_cnt,
        'passed':  ok_cnt,
        'failed':  fail_cnt,
        'elapsed_ms': int((time.time()-t0)*1000),
    }
