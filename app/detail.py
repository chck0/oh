"""
단지 상세/조회 라우터 (spec-17, spec-20, spec-26)

GET /api/apt/{apt_seq}/routes      : 통근 경로 옵션 (rank 1~N)
GET /api/search/apt-lookup         : 단지명 직접 검색 (spec-26)
GET /api/apt/{apt_seq}/detail      : 상세 패널 (거래내역 + POI + 시세차트)

search.py에서 router.include_router(detail_router)로 합쳐진다.
search 모듈을 import하지 않으므로 순환 의존 없음.
"""
import asyncio

from fastapi import APIRouter, Depends

from app.db import get_db, connect as db_connect
from app.portable import year_minus
from config import cfg

router = APIRouter()


# ── GET /api/apt/{apt_seq}/routes ────────────────────────────
@router.get("/apt/{apt_seq}/routes")
def apt_routes(apt_seq: str, wp_id: int, conn=Depends(get_db)):
    """단지 상세 — 모든 경로 옵션 (rank 1~N)"""
    # 뷰(v_apt_transit_options)는 SQLite 쿼리 플래너가 apt_seq 조건을 뷰 안으로 밀어넣지 못해
    # 전체 스캔 → 7초 소요. 2단계 조회(grid_key 먼저 → transit_routes 직접)로 0.001초로 단축.
    gk_row = conn.execute(
        "SELECT grid_key FROM apartments WHERE apt_seq=?", [apt_seq]
    ).fetchone()
    if not gk_row or not gk_row['grid_key']:
        return {'apt_seq': apt_seq, 'wp_id': wp_id, 'options': []}

    rows = conn.execute("""
        SELECT rank, total_time_min, bus_cnt, subway_cnt,
               step1_type, step1_time_min, step1_dist_m, step1_노선, step1_출발, step1_도착, step1_linestring,
               step2_type, step2_time_min, step2_dist_m, step2_노선, step2_출발, step2_도착, step2_linestring,
               step3_type, step3_time_min, step3_dist_m, step3_노선, step3_출발, step3_도착, step3_linestring,
               step4_type, step4_time_min, step4_dist_m, step4_노선, step4_출발, step4_도착, step4_linestring,
               step5_type, step5_time_min, step5_dist_m, step5_노선, step5_출발, step5_도착, step5_linestring
        FROM transit_routes
        WHERE origin_cell=? AND wp_id=?
        ORDER BY rank
    """, [gk_row['grid_key'], wp_id]).fetchall()

    options = []
    for r in rows:
        steps = []
        for i in range(5):
            off = 4 + i*7   # 각 step당 7개 컬럼 (type, time_min, dist_m, 노선, 출발, 도착, linestring)
            t = r[off]
            if not t:
                continue
            steps.append({
                'type':       t,
                'time_min':   r[off+1],
                'dist_m':     r[off+2],
                'line':       r[off+3],
                'from':       r[off+4],
                'to':         r[off+5],
                'linestring': r[off+6],   # baked (GTFS순서+OSM역쌍곡선, Spec31)
            })
        options.append({
            'rank': r['rank'],
            'total_time_min': r['total_time_min'],
            'bus_cnt': r['bus_cnt'],
            'subway_cnt': r['subway_cnt'],
            'steps': steps,
        })
    return {'apt_seq': apt_seq, 'wp_id': wp_id, 'options': options}


# ── GET /api/search/apt-lookup  (spec-26: 분석결과 직접 검색) ──
@router.get("/search/apt-lookup")
def search_apt_lookup(
    name: str = "",
    wp_id: int = 0,
    pyeong_type: str = "20평대",
    conn=Depends(get_db),
):
    if len(name.strip()) < 2:
        return {"results": []}

    apts = conn.execute(
        "SELECT apt_seq, apt_nm, umd_nm, lat, lng, kaptdaCnt, build_year "
        "FROM apartments WHERE apt_nm LIKE ? "
        "ORDER BY kaptdaCnt DESC LIMIT 5",
        [f"%{name.strip()}%"],
    ).fetchall()

    results = []
    for apt in apts:
        trade = conn.execute(
            "SELECT price_low, price_high FROM trade_recent "
            "WHERE apt_seq=? AND pyeong_type=? LIMIT 1",
            [apt["apt_seq"], pyeong_type],
        ).fetchone()

        transit = conn.execute(
            "SELECT MIN(total_time) AS transit_min FROM transit_cache "
            "WHERE wp_id=? AND passed_filter=1 "
            "  AND origin_cell=(SELECT grid_key FROM apartments WHERE apt_seq=? LIMIT 1)",
            [wp_id, apt["apt_seq"]],
        ).fetchone()

        results.append(
            {
                "apt_seq":    apt["apt_seq"],
                "apt_nm":     apt["apt_nm"],
                "umd_nm":     apt["umd_nm"],
                "lat":        apt["lat"],
                "lng":        apt["lng"],
                "kaptdaCnt":  apt["kaptdaCnt"],
                "build_year": apt["build_year"],
                "pyeong_type": pyeong_type,
                "price_low":  trade["price_low"]  if trade else None,
                "price_high": trade["price_high"] if trade else None,
                "transit_min": transit["transit_min"] if transit and transit["transit_min"] else None,
            }
        )

    return {"results": results}


# ── GET /api/apt/{apt_seq}/detail ────────────────────────────
@router.get("/apt/{apt_seq}/detail")
async def apt_detail(apt_seq: str, wp_id: int):
    """
    상세 패널용 — 거래내역 + POI + 시세차트 데이터
    통근경로는 /routes 엔드포인트를 별도 호출

    쿼리 7개 병렬화: apt(umd_nm 의존) 먼저 1회, 나머지 6개를 asyncio.gather로
    동시 실행. 각 쿼리는 풀에서 커넥션을 빌려 독립 스레드에서 돈다.
    (Tokyo 시절 순차 ~480ms → 병렬 ~2회 왕복으로 단축)
    """
    import time
    timings = {}
    t0 = time.time()
    threshold_year = year_minus(3)  # 3년 전 YYYY

    # ── Phase 1: 기본 단지 정보 (umd_nm 확보 + early return) ──────
    def _q_apt():
        c = db_connect()
        try:
            return c.execute("""
                SELECT a.apt_nm, a.umd_nm, a.kaptdaCnt, a.lat, a.lng,
                       k.kaptUsedate, k.kaptTopFloor, k.kaptBaseFloor,
                       k.kaptDongCnt, k.kaptdEcnt,
                       k.kaptdCccnt, k.kaptdPcnt, k.kaptdPcntu,
                       k.codeHeatNm, k.codeHallNm,
                       k.kaptBcompany,
                       k.groundElChargerCnt, k.undergroundElChargerCnt,
                       k.subwayLine, k.subwayStation, k.kaptdWtimesub
                FROM apartments a
                LEFT JOIN kapt_complexes k USING(kaptCode)
                WHERE a.apt_seq = ?
            """, [apt_seq]).fetchone()
        finally:
            c.close()
    apt = await asyncio.to_thread(_q_apt)
    timings['apt_info'] = round((time.time()-t0)*1000)
    if not apt:
        print(f'[detail {apt_seq}] 단지 없음 — timings: {timings}')
        return {}
    umd_nm = apt['umd_nm']

    # ── Phase 2: 나머지 6개 쿼리 병렬 (각자 풀 커넥션) ────────────
    def _q_fc():
        c = db_connect()
        try:
            return c.execute(
                'SELECT pyeong_type, comment FROM apt_pt_friend_comment '
                'WHERE apt_seq=? AND wp_id=? ORDER BY LENGTH(comment) DESC',
                [apt_seq, wp_id]
            ).fetchall()
        finally:
            c.close()

    def _q_tabs():
        c = db_connect()
        try:
            return c.execute("""
                SELECT pyeong_type, pyeong,
                       COUNT(*) AS deal_count,
                       MIN(deal_amount_int) AS price_min,
                       MAX(deal_amount_int) AS price_max
                FROM trade_history
                WHERE apt_seq = ?
                  AND deal_year >= ?
                GROUP BY pyeong_type, pyeong
                ORDER BY deal_count DESC
            """, [apt_seq, threshold_year]).fetchall()
        finally:
            c.close()

    def _q_chart():
        c = db_connect()
        try:
            return c.execute("""
                SELECT pyeong_type, pyeong, deal_year, deal_month,
                       ROUND(AVG(deal_amount_int)) AS avg_amount,
                       COUNT(*) AS cnt
                FROM trade_history
                WHERE apt_seq = ?
                  AND deal_year >= ?
                GROUP BY pyeong_type, pyeong, deal_year, deal_month
                ORDER BY pyeong_type, deal_year, deal_month
            """, [apt_seq, threshold_year]).fetchall()
        finally:
            c.close()

    def _q_dong():
        c = db_connect()
        try:
            return c.execute("""
                SELECT pyeong_type, deal_year, deal_month,
                       ROUND(AVG(deal_amount_int)) AS avg_amount,
                       COUNT(*) AS cnt
                FROM trade_history
                WHERE umd_nm = ?
                  AND deal_year >= ?
                GROUP BY pyeong_type, deal_year, deal_month
                ORDER BY pyeong_type, deal_year, deal_month
            """, [umd_nm, threshold_year]).fetchall()
        finally:
            c.close()

    def _q_trades():
        c = db_connect()
        try:
            return c.execute("""
                SELECT deal_year, deal_month, deal_day,
                       pyeong, pyeong_type, deal_amount_int, floor
                FROM trade_recent
                WHERE apt_seq = ?
                UNION
                SELECT deal_year, deal_month, deal_day,
                       pyeong, pyeong_type, deal_amount_int, floor
                FROM trade_history
                WHERE apt_seq = ?
                  AND deal_year >= ?
                ORDER BY deal_year DESC, deal_month DESC, deal_day DESC
                LIMIT 20
            """, [apt_seq, apt_seq, threshold_year]).fetchall()
        finally:
            c.close()

    def _q_poi():
        c = db_connect()
        try:
            return c.execute("""
                SELECT poi_lclas_cd, poi_mlsfc_cd, poi_nm, distance_m, walking_min
                FROM apt_walking_poi
                WHERE kaptCode = (
                    SELECT kaptCode FROM apartments WHERE apt_seq = ? LIMIT 1
                )
                  AND walking_min <= ?
                ORDER BY distance_m
                LIMIT 50
            """, [apt_seq, cfg.POI_WALK_MAX_MIN]).fetchall()
        finally:
            c.close()

    fc_rows, pyeong_tabs, chart_rows, dong_avg_rows, trade_rows, poi_rows = await asyncio.gather(
        asyncio.to_thread(_q_fc),
        asyncio.to_thread(_q_tabs),
        asyncio.to_thread(_q_chart),
        asyncio.to_thread(_q_dong),
        asyncio.to_thread(_q_trades),
        asyncio.to_thread(_q_poi),
    )
    timings['parallel_6q'] = round((time.time()-t0)*1000)

    # 주차대수: kaptdPcnt(지하) + kaptdPcntu(지상)
    def _to_int(v):
        try:
            return int(v or 0)
        except (ValueError, TypeError):
            return 0
    parking_underground = _to_int(apt['kaptdCccnt'])
    parking_ground = _to_int(apt['kaptdPcntu'])
    parking_total = (
        parking_underground + parking_ground
        if (parking_underground or parking_ground) else None
    )

    # 준공연도
    use_date = apt['kaptUsedate'] or ''
    build_year = int(use_date[:4]) if len(use_date) >= 4 and use_date[:4].isdigit() else None

    # 전기차 충전기
    ev_chargers = _to_int(apt['groundElChargerCnt']) + _to_int(apt['undergroundElChargerCnt'])

    building_info = {
        'build_year':   build_year,
        'top_floor':    apt['kaptTopFloor'],
        'base_floor':   apt['kaptBaseFloor'],
        'dong_cnt':     apt['kaptDongCnt'],
        'elevator_cnt': apt['kaptdEcnt'],
        'parking':      parking_total,
        'heat_type':    apt['codeHeatNm'],
        'hall_type':    apt['codeHallNm'],
        'builder':      apt['kaptBcompany'],
        'ev_chargers':  ev_chargers if ev_chargers else None,
        'subway_line':  apt['subwayLine'],
        'subway_sta':   apt['subwayStation'],
        'subway_walk':  apt['kaptdWtimesub'],
    }

    # ── 친구 한 마디 (detail은 단지 통합 → 가장 긴 코멘트 우선) ──
    friend_comment = fc_rows[0]['comment'] if fc_rows else None
    tier = None  # 신규 컨셉엔 tier 없음

    # ── 평수 탭 목록 (거래 많은 순, 디폴트=1위) ─────────────────
    tabs = [
        {
            'pyeong_type': r['pyeong_type'],
            'pyeong': r['pyeong'],
            'deal_count': r['deal_count'],
            'price_min': r['price_min'],
            'price_max': r['price_max'],
        }
        for r in pyeong_tabs
    ]
    # ── 시세 차트 (chart_rows / dong_avg_rows는 위에서 병렬 prefetch됨) ──
    # ym 문자열은 deal_year/deal_month로 Python에서 포맷
    # dict 구조로 변환 {pyeong_type: {ym: avg_amount}}
    complex_chart: dict = {}
    for r in chart_rows:
        key = f"{r['pyeong_type']}_{r['pyeong']}"
        ym = f"{r['deal_year']}-{r['deal_month']:02d}"
        complex_chart.setdefault(key, {})[ym] = int(r['avg_amount'])

    dong_chart: dict = {}
    for r in dong_avg_rows:
        ym = f"{r['deal_year']}-{r['deal_month']:02d}"
        dong_chart.setdefault(r['pyeong_type'], {})[ym] = int(r['avg_amount'])

    # ── 최근 실거래 내역 (trade_rows는 위에서 병렬 prefetch됨) ──
    trades = [
        {
            'date': f"{r['deal_year']}.{r['deal_month']:02d}.{r['deal_day']:02d}",
            'pyeong': r['pyeong'],
            'pyeong_type': r['pyeong_type'],
            'amount': r['deal_amount_int'],
            'floor': r['floor'],
        }
        for r in trade_rows
    ]

    # ── 도보 POI (poi_rows는 위에서 병렬 prefetch됨) ────────────
    poi = [
        {
            'category': r['poi_lclas_cd'],
            'sub_category': r['poi_mlsfc_cd'],
            'name': r['poi_nm'],
            'distance_m': r['distance_m'],
            'walking_min': r['walking_min'],
        }
        for r in poi_rows
    ]

    # ── 시세 요약 지표 (6개월 변화, 동 대비) ──────────────────
    # 가장 많이 거래된 평수로 계산
    price_summary = {}
    if tabs:
        top_pyeong_type = tabs[0]['pyeong_type']
        top_pyeong      = tabs[0]['pyeong']
        key = f"{top_pyeong_type}_{top_pyeong}"
        series = complex_chart.get(key, {})
        months_sorted = sorted(series.keys())
        if len(months_sorted) >= 7:
            recent  = series[months_sorted[-1]]
            six_ago = series[months_sorted[-7]]
            chg_pct = round((recent - six_ago) / six_ago * 100, 1) if six_ago else None
        else:
            chg_pct = None

        dong_series  = dong_chart.get(top_pyeong_type, {})
        dong_months  = sorted(dong_series.keys())
        dong_recent  = dong_series.get(dong_months[-1]) if dong_months else None
        apt_recent   = series.get(months_sorted[-1]) if months_sorted else None
        vs_dong_pct = (
            round((apt_recent - dong_recent) / dong_recent * 100, 1)
            if (apt_recent and dong_recent) else None
        )
        vs_dong_diff = (
            int(apt_recent - dong_recent)
            if (apt_recent and dong_recent) else None
        )

        price_summary = {
            'pyeong_type': top_pyeong_type,
            'pyeong': top_pyeong,
            'change_6m_pct': chg_pct,
            'vs_dong_pct':   vs_dong_pct,
            'vs_dong_diff':  vs_dong_diff,
        }

    timings['TOTAL'] = round((time.time()-t0)*1000)
    print(f'[detail {apt_seq}] timings(ms): {timings}')

    return {
        'apt_seq':   apt_seq,
        'apt_nm':    apt['apt_nm'],
        'umd_nm':    umd_nm,
        'kaptdaCnt': apt['kaptdaCnt'],
        'lat':       apt['lat'],
        'lng':       apt['lng'],
        'tier':           tier,
        'friend_comment': friend_comment,
        'building':       building_info,
        'pyeong_tabs':    tabs,
        'chart': {
            'complex': complex_chart,
            'dong':    dong_chart,
        },
        'price_summary': price_summary,
        'trades': trades,
        'poi':    poi,
    }
