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


# ── 입지·구조 지표 라벨 변환 (spec-31) ───────────────────────
# 경사: 도(°) 원본은 툴팁용으로만 두고, 본문엔 체감 라벨+한 줄 설명으로 번역.
#   ⚠️ apt_slope_avg 단위가 도(°) 가정. 프로덕션 데이터로 단위 확인 시 임계값만 조정.
def _slope_label(avg) -> tuple[str, str, int] | None:
    """단지 평균 경사(도) → (라벨, 한 줄 체감 설명, 레벨 1~4). 비정상값은 None.

    레벨은 프론트 인디케이터 칸 수와 직결 — 라벨 문자열에 의존하지 않도록 백엔드가 산출.
    """
    try:
        v = float(avg)
    except (TypeError, ValueError):
        return None
    if v < 0:
        v = 0.0  # 음수 이상치는 평지 취급
    if v < 3:
        return ('평지', '걷기 편해요', 1)
    if v < 7:
        return ('완만한 오르막', '살짝 오르막이에요', 2)
    if v < 12:
        return ('언덕', '오르막이 확실히 느껴져요', 3)
    return ('가파른 언덕', '짐 들고 오르긴 부담돼요', 4)


def _far_level(far) -> str | None:
    """용적률(%) → 낮은 편/보통/높은 편. 아파트 대개 200~250% 기준."""
    try:
        v = float(far)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    if v < 180:
        return '낮은 편'
    if v <= 280:
        return '보통'
    return '높은 편'


def _bcr_level(bcr) -> str | None:
    """건폐율(%) → 낮은 편(동 간격 여유)/보통/높은 편. 대개 15~25% 기준."""
    try:
        v = float(bcr)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    if v < 15:
        return '낮은 편'
    if v <= 25:
        return '보통'
    return '높은 편'


def _approve_ym(use_apr_day) -> str | None:
    """사용승인일 YYYYMMDD → 'YYYY.MM'. 형식 비정상은 None."""
    s = str(use_apr_day or '').strip()
    if len(s) >= 6 and s[:6].isdigit():
        mm = s[4:6]
        if '01' <= mm <= '12':
            return f'{s[:4]}.{mm}'
    return None


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
               step1_type, step1_time_min, step1_dist_m, step1_노선, step1_출발, step1_도착,
               step2_type, step2_time_min, step2_dist_m, step2_노선, step2_출발, step2_도착,
               step3_type, step3_time_min, step3_dist_m, step3_노선, step3_출발, step3_도착,
               step4_type, step4_time_min, step4_dist_m, step4_노선, step4_출발, step4_도착,
               step5_type, step5_time_min, step5_dist_m, step5_노선, step5_출발, step5_도착
        FROM transit_routes
        WHERE origin_cell=? AND wp_id=?
        ORDER BY rank
    """, [gk_row['grid_key'], wp_id]).fetchall()

    options = []
    for r in rows:
        steps = []
        for i in range(5):
            off = 4 + i*6   # 각 step당 6개 컬럼 (type, time_min, dist_m, 노선, 출발, 도착)
            t = r[off]
            if not t:
                continue
            steps.append({
                'type': t,
                'time_min': r[off+1],
                'dist_m':   r[off+2],
                'line':     r[off+3],
                'from':     r[off+4],
                'to':       r[off+5],
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

    # 입지·구조 (spec-31): apt_slope(1행) + building_register(동별 다행).
    # 각 테이블을 독립 try/except 로 보호 — 미존재/실패해도 상세 나머지는 정상.
    # 전용 커넥션이라 실패 시 rollback 으로 상태 복구 (pgBouncer InFailedSqlTransaction 방지).
    def _q_infra():
        c = db_connect()
        slope_row = None
        br_rows = []
        try:
            try:
                slope_row = c.execute(
                    'SELECT apt_slope_avg FROM apt_slope WHERE kaptCode = '
                    '(SELECT kaptCode FROM apartments WHERE apt_seq = ? LIMIT 1)',
                    [apt_seq]
                ).fetchone()
            except Exception:
                try:
                    c.rollback()
                except Exception:
                    pass
            try:
                br_rows = c.execute(
                    'SELECT vlRat, bcRat, strctCdNm, useAprDay FROM building_register '
                    'WHERE kaptCode = '
                    '(SELECT kaptCode FROM apartments WHERE apt_seq = ? LIMIT 1)',
                    [apt_seq]
                ).fetchall()
            except Exception:
                try:
                    c.rollback()
                except Exception:
                    pass
        finally:
            c.close()
        return slope_row, br_rows

    (fc_rows, pyeong_tabs, chart_rows, dong_avg_rows, trade_rows, poi_rows,
     infra) = await asyncio.gather(
        asyncio.to_thread(_q_fc),
        asyncio.to_thread(_q_tabs),
        asyncio.to_thread(_q_chart),
        asyncio.to_thread(_q_dong),
        asyncio.to_thread(_q_trades),
        asyncio.to_thread(_q_poi),
        asyncio.to_thread(_q_infra),
    )
    timings['parallel_7q'] = round((time.time()-t0)*1000)

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

    # ── 입지·구조 지표 병합 (spec-31) — 값 있는 항목만 추가 ──────
    slope_row, br_rows = infra
    if slope_row and slope_row['apt_slope_avg'] is not None:
        labeled = _slope_label(slope_row['apt_slope_avg'])
        if labeled:
            building_info['slope_avg'] = round(float(slope_row['apt_slope_avg']), 1)
            building_info['slope_label'] = labeled[0]
            building_info['slope_hint'] = labeled[1]
            building_info['slope_level'] = labeled[2]
    if br_rows:
        from collections import Counter
        # 0/음수는 건축물대장 미집계(누락)로 취급 → 행 숨김 (0% 오표시 방지)
        fars = [r['vlRat'] for r in br_rows if r['vlRat'] is not None and r['vlRat'] > 0]
        bcrs = [r['bcRat'] for r in br_rows if r['bcRat'] is not None and r['bcRat'] > 0]
        strs = [r['strctCdNm'] for r in br_rows if r['strctCdNm']]
        # YYYYMMDD 8자리만 후보 → min() 이 짧은 비정상값을 고르지 않도록
        days = [s for r in br_rows
                if (s := str(r['useAprDay'] or '').strip())[:8].isdigit() and len(s) >= 8]
        if fars:
            far = round(sum(fars) / len(fars), 1)
            building_info['far'] = far
            building_info['far_level'] = _far_level(far)
        if bcrs:
            bcr = round(sum(bcrs) / len(bcrs), 1)
            building_info['bcr'] = bcr
            building_info['bcr_level'] = _bcr_level(bcr)
        if strs:
            building_info['structure'] = Counter(strs).most_common(1)[0][0]
        if days:
            approve = _approve_ym(min(days))
            if approve:
                building_info['approve_ym'] = approve

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
