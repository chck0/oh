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
PER_KEY_CONCURRENCY = 2
ROUND_SLEEP_MS      = 300
HTTP_TIMEOUT        = 15

ALLOWED_COMBOS    = {(0,1),(0,2),(1,0),(2,0),(1,1)}
WALK_ONLY_MAX_MIN = 15
FIRST_LAST_WALK_M = 840
TRANSFER_WALK_M   = 420

KEYS = [{'owner': f'key{i+1}', **k} for i, k in enumerate(cfg.ODSAY_KEYS)]

# ── transit_routes 컬럼 구조 ─────────────────────────────────
# step이 추가될 때는 MAX_STEPS 숫자만 바꾸면 INSERT/SELECT 자동 반영.
MAX_STEPS = 5
_STEP_FIELDS = ('type', 'time_min', 'dist_m', '노선', '출발', '도착')
_ROUTE_BASE_COLS = ['origin_cell', 'wp_id', 'rank',
                    'total_time_min', 'bus_cnt', 'subway_cnt']
_ROUTE_STEP_COLS = [f'step{n}_{f}' for n in range(1, MAX_STEPS + 1)
                    for f in _STEP_FIELDS]
_ROUTE_ALL_COLS  = _ROUTE_BASE_COLS + _ROUTE_STEP_COLS

_ROUTE_INSERT_SQL = (
    f'INSERT INTO transit_routes ({", ".join(_ROUTE_ALL_COLS)}) '
    f'VALUES ({", ".join(["?"] * len(_ROUTE_ALL_COLS))})'
)

_CLASS_MAP = {'버스': 1, '지하철': 2}


def _geom_near(poly, x, y):
    best, bi = 1e18, 0
    for i, (px, py) in enumerate(poly):
        d = (px - x) ** 2 + (py - y) ** 2
        if d < best:
            best, bi = d, i
    return bi


def _geom_clip(whole, board, alight):
    a = _geom_near(whole, *board)
    b = _geom_near(whole, *alight)
    lo, hi = (a, b) if a <= b else (b, a)
    seg = whole[lo:hi + 1]
    return seg[::-1] if a > b else seg


def _geom_legs(path):
    """ODsay path → 교통 leg [(lineID, class, board_xy, alight_xy)]."""
    mo = path.get('info', {}).get('mapObj') or ''
    segs = []
    for s in mo.split('@'):
        pr = s.split(':')
        if len(pr) >= 2 and pr[1] in ('1', '2'):
            segs.append((pr[0], int(pr[1])))
    tsubs = [sp for sp in path.get('subPath', []) if sp.get('trafficType') in (1, 2)]
    if len(segs) != len(tsubs):
        return None
    legs = []
    for (lid, cls), sp in zip(segs, tsubs):
        sts = (sp.get('passStopList') or {}).get('stations') or []
        if len(sts) < 2:
            board  = (float(sp['startX']), float(sp['startY']))
            alight = (float(sp['endX']),   float(sp['endY']))
        else:
            board  = (float(sts[0]['x']),  float(sts[0]['y']))
            alight = (float(sts[-1]['x']), float(sts[-1]['y']))
        legs.append((lid, cls, board, alight))
    return legs


def _load_line_geom(conn):
    """line_geom 테이블 전체 로드. SQLite에 없으면 빈 dict 반환."""
    try:
        rows = conn.execute(
            "SELECT line_id, class, ls FROM line_geom WHERE status='ok' AND ls IS NOT NULL"
        ).fetchall()
        return {
            (r[0], r[1]): [tuple(map(float, pt.split(','))) for pt in r[2].split()]
            for r in rows
        }
    except Exception:
        return {}


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
                steps.append({'type':'환승도보','time':t,'dist':0, 'line':'','from':'','to':''})
            else:
                steps.append({'type':'도보','time':t,'dist':d, 'line':'','from':'','to':''})
        elif tt == 1:
            lane = sp.get('lane', [{}])[0]
            steps.append({'type':'지하철','time':t,'dist':d,
                          'line': lane.get('name',''),
                          'from': sp.get('startName',''), 'to': sp.get('endName','')})
        elif tt == 2:
            lane = sp.get('lane', [{}])[0]
            steps.append({'type':'버스','time':t,'dist':d,
                          'line': lane.get('busNo',''),
                          'from': sp.get('startName',''), 'to': sp.get('endName','')})
    return steps[:5]


def step_cols(steps, n):
    if n <= len(steps):
        s = steps[n-1]
        return s['type'], s['time'], s['dist'], s['line'], s['from'], s['to']
    return '', None, None, '', '', ''


# ── ODsay 호출 ───────────────────────────────────────────────
async def _call_one(session, key_info, sem, origin_cell, dest_lat, dest_lng):
    async with sem:
        o_lat, o_lng = cell_center(origin_cell)
        params = {
            'apiKey': key_info['key'],
            'SX': o_lng, 'SY': o_lat, 'EX': dest_lng, 'EY': dest_lat,
            'lang': 0, 'OPT': 0
        }
        headers = {'Referer': key_info['referer']}
        try:
            async with session.get(
                ODSAY_URL, params=params, headers=headers,
                timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT),
            ) as r:
                raw  = await r.text()
                data = json.loads(raw)
                if 'result' not in data:
                    log.warning(
                        'ODsay no-result [%s] key=%s status=%d body=%s',
                        origin_cell, key_info['owner'], r.status, raw[:300],
                    )
                    # ApiKey 인증 실패 → 캐시 절대 X. raw='' 반환 → 호출자가
                    # response_size=0 으로 저장 → 다음 검색에서 다른 키로 재시도.
                    err = data.get('error')
                    err_msg = ''
                    if isinstance(err, list) and err:
                        err_msg = str(err[0].get('message', ''))
                    elif isinstance(err, dict):
                        err_msg = str(err.get('message', ''))
                    if 'ApiKeyAuthFailed' in err_msg or 'apikey' in err_msg.lower():
                        return origin_cell, [], ''  # 캐시 X
                    return origin_cell, [], raw    # 캐시 O (legit no-transit)
                return origin_cell, rank_paths(data['result'].get('path', [])), raw
        except Exception as e:
            log.error('ODsay exception [%s] key=%s: %s', origin_cell, key_info['owner'], e)
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

    sems = {k['owner']: asyncio.Semaphore(PER_KEY_CONCURRENCY) for k in KEYS}
    ROUND_SIZE = len(KEYS) * PER_KEY_CONCURRENCY
    rounds = (len(cells_to_fetch) + ROUND_SIZE - 1) // ROUND_SIZE

    cells_dir = None
    if not IS_SERVERLESS:
        cells_dir = raw_dir(wp_row) / 'cells'
        cells_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    ok_cnt = fail_cnt = 0
    cache_inserts, route_inserts = [], []
    ranked_by_origin: dict[str, list] = {}   # linestring 백필용 raw path 보관
    now = time.strftime('%Y-%m-%d %H:%M:%S')

    # 동시 연결 한도 = 키수 × 키당동시성(=ROUND_SIZE)에 자동 비례 + 약간의 여유.
    # 고정 30이면 키를 늘려도(예: 15키×4=60) 30에서 큐잉돼 증설 효과가 반감된다.
    # 키를 추가하면 코드 수정 없이 동시성이 따라 오른다. 하한 30 보장.
    conn_limit = max(30, ROUND_SIZE + 4)
    connector = aiohttp.TCPConnector(limit=conn_limit, ttl_dns_cache=300)
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
                    ranked_by_origin[origin] = ranked
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

    # ── linestring 인라인 백필 (line_geom이 DB에 있을 때만) ──────
    if ranked_by_origin:
        line_geom = _load_line_geom(conn)
        if line_geom:
            ls_updates = []
            setc = ', '.join(f'step{n}_linestring=?' for n in range(1, MAX_STEPS + 1))
            for origin, ranked in ranked_by_origin.items():
                for rank, p in ranked:
                    legs = _geom_legs(p)
                    if not legs:
                        continue
                    steps = to_steps(p['subPath'])
                    linestrings = [None] * MAX_STEPS
                    li = 0
                    for k, s in enumerate(steps[:MAX_STEPS]):
                        if _CLASS_MAP.get(s['type']) is None:
                            continue
                        if li >= len(legs):
                            break
                        lid, cls, board, alight = legs[li]; li += 1
                        whole = line_geom.get((lid, cls))
                        if whole:
                            seg = _geom_clip(whole, board, alight)
                            if len(seg) >= 2:
                                linestrings[k] = ' '.join(f'{x},{y}' for x, y in seg)
                    if any(ls for ls in linestrings):
                        ls_updates.append((*linestrings, origin, wp_id, rank))
            if ls_updates:
                conn.executemany(
                    f'UPDATE transit_routes SET {setc} WHERE origin_cell=? AND wp_id=? AND rank=?',
                    ls_updates,
                )
                log.info('linestring 백필: %d행', len(ls_updates))

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
