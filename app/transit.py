"""
ODsay 호출 + transit_cache/routes 적재
(sandbox/51, 52 통합 → production용)

Vercel(서버리스)에서는 raw JSON 아카이브 쓰기를 자동 스킵 (IS_SERVERLESS).
"""
import os, asyncio, aiohttp, sqlite3, json, time, math, logging
from config import cfg
from app.workplaces import raw_dir, cell_file
from app.portable import upsert_sql

IS_SERVERLESS = bool(os.getenv('VERCEL'))
log = logging.getLogger('app.transit')

GRID                = 0.0045
ODSAY_URL           = "https://api.odsay.com/v1/api/searchPubTransPathT"
# 동시성 2→4, 슬립 300→100 — Vercel 60s 한도 내 더 많은 셀 처리.
# ODsay 키 4개 × 4 = 16 병렬, rate limit 측면에선 키당 4req/s 정도라 안전권.
PER_KEY_CONCURRENCY = 4
ROUND_SLEEP_MS      = 100
HTTP_TIMEOUT        = 15

ALLOWED_COMBOS    = {(0,1),(0,2),(1,0),(2,0),(1,1)}
WALK_ONLY_MAX_MIN = 15
FIRST_LAST_WALK_M = 840
TRANSFER_WALK_M   = 420

KEYS = [{'owner': f'key{i+1}', **k} for i, k in enumerate(cfg.ODSAY_KEYS)]


# ── 좌표 유틸 ────────────────────────────────────────────────
def cell_of(lat, lng):
    return f"R{int(lat/GRID):05d}C{int(lng/GRID):05d}"

def cell_center(cell_code):
    return (int(cell_code[1:6]) + 0.5) * GRID, (int(cell_code[7:12]) + 0.5) * GRID

def haversine(lat1, lng1, lat2, lng2):
    R = 6371
    dlat = math.radians(lat2 - lat1); dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlng/2)**2)
    return R * 2 * math.asin(math.sqrt(a))


# ── 경로 필터 + 랭킹 ──────────────────────────────────────────
def filter_path(p):
    info = p['info']; bt = info['busTransitCount']; st = info['subwayTransitCount']
    subs = p['subPath']
    if bt == 0 and st == 0:
        return info['totalTime'] <= WALK_ONLY_MAX_MIN
    if (bt, st) not in ALLOWED_COMBOS:                       return False
    if subs[0].get('distance', 0) > FIRST_LAST_WALK_M:       return False
    if subs[-1].get('distance', 0) > FIRST_LAST_WALK_M:      return False
    for sp in subs[1:-1]:
        if sp.get('trafficType') == 3 and sp.get('distance', 0) > TRANSFER_WALK_M:
            return False
    return True


def rank_paths(paths):
    valid = [p for p in paths if filter_path(p)]
    def pri(p):
        bt = p['info']['busTransitCount']; st = p['info']['subwayTransitCount']
        cls = {(0,1):1,(1,1):2,(0,2):3,(1,0):4}.get((bt,st), 5)
        return (cls, p['info']['totalTime'])
    valid.sort(key=pri)
    return [(i+1, p) for i, p in enumerate(valid)]


def to_steps(subpath_list):
    steps = []
    for sp in subpath_list:
        tt = sp.get('trafficType'); t = sp.get('sectionTime', 0); d = sp.get('distance', 0)
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
            async with session.get(ODSAY_URL, params=params, headers=headers,
                                    timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT)) as r:
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
                        s1, s2, s3, s4, s5 = [step_cols(steps, i) for i in (1,2,3,4,5)]
                        route_inserts.append((
                            origin, wp_id, rank,
                            info['totalTime'], info['busTransitCount'], info['subwayTransitCount'],
                            *s1, *s2, *s3, *s4, *s5
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

    conn.executemany("""
    INSERT INTO transit_routes (
        origin_cell, wp_id, rank, total_time_min, bus_cnt, subway_cnt,
        step1_type, step1_time_min, step1_dist_m, step1_노선, step1_출발, step1_도착,
        step2_type, step2_time_min, step2_dist_m, step2_노선, step2_출발, step2_도착,
        step3_type, step3_time_min, step3_dist_m, step3_노선, step3_출발, step3_도착,
        step4_type, step4_time_min, step4_dist_m, step4_노선, step4_출발, step4_도착,
        step5_type, step5_time_min, step5_dist_m, step5_노선, step5_출발, step5_도착
    ) VALUES (?,?,?,?,?,?, ?,?,?,?,?,?, ?,?,?,?,?,?, ?,?,?,?,?,?, ?,?,?,?,?,?, ?,?,?,?,?,?)
    """, route_inserts)

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
