"""
단지 상세/조회 라우터 (spec-17, spec-20, spec-26)

GET /api/apt/{apt_seq}/routes      : 통근 경로 옵션 (rank 1~N)
GET /api/search/apt-lookup         : 단지명 직접 검색 (spec-26)
GET /api/apt/{apt_seq}/detail      : 상세 패널 (거래내역 + POI + 시세차트)

search.py에서 router.include_router(detail_router)로 합쳐진다.
search 모듈을 import하지 않으므로 순환 의존 없음.
"""
import asyncio

from fastapi import APIRouter, Depends, Response

from app.db import get_db, connect as db_connect
from app.portable import year_minus
from config import cfg

router = APIRouter()

# dong(동) 평균 시세 인메모리 캐시 — (umd_nm, threshold_year) → (ts, rows).
# 같은 동의 모든 단지가 동일 결과라 같은 지역 연속 탐색 시 재계산을 제거한다.
# 거래 데이터는 배치로 드물게 갱신되므로 짧은 TTL로 충분(최대 TTL만큼만 stale).
_DONG_CACHE: dict = {}
_DONG_TTL = 600  # 초


# ── 입지·구조 지표 라벨 변환 (spec-31) ───────────────────────
# 경사: 도(°) 원본은 툴팁용으로만 두고, 본문엔 체감 라벨+한 줄 설명으로 번역.
#   ⚠️ apt_slope_avg 단위가 도(°) 가정. 프로덕션 데이터로 단위 확인 시 임계값만 조정.
#
# 2026-06-13 임시 비활성: 운영에서 대부분 단지가 '언덕/가파른 언덕'으로 표기됨.
# apt_slope_avg 단위(도°/% 구배) 미확정 → 라벨이 틀렸을 가능성 높음(잘못된 단정 = 신뢰 저하).
# 실데이터 분포 검증 + 임계값 재보정 전까지 경사 행을 내림. (용적률/건폐율/구조/사용승인은 유지)
SLOPE_LABEL_ENABLED = False
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


# transit_routes 형상 dedup 스키마 감지 (stepN_geom_id + route_geom). 1회 탐지 후 캐시.
# dedup이면 route_geom JOIN으로 linestring 복원, 아니면(현 운영 구 스키마) 기존 컬럼 그대로.
# 두 경우 컬럼 순서를 동일하게 맞춰 아래 파싱 로직(off=4+i*7)을 불변으로 유지.
_DEDUP_SCHEMA = None


def _routes_query(conn) -> str:
    global _DEDUP_SCHEMA
    if _DEDUP_SCHEMA is None:
        try:
            # 컬럼 존재 여부 + 실제로 값이 채워져 있는지 동시 확인.
            # 컬럼만 있고 전부 NULL이면 dedup 미완성 → 구 스키마(step{i}_linestring)로 폴백.
            row = conn.execute(
                "SELECT step1_geom_id FROM transit_routes WHERE step1_geom_id IS NOT NULL LIMIT 1"
            ).fetchone()
            _DEDUP_SCHEMA = row is not None
        except Exception:
            _DEDUP_SCHEMA = False
    if _DEDUP_SCHEMA:
        step_sel = ", ".join(
            f"tr.step{i}_type, tr.step{i}_time_min, tr.step{i}_dist_m, "
            f"tr.step{i}_노선, tr.step{i}_출발, tr.step{i}_도착, "
            f"COALESCE(g{i}.ls, tr.step{i}_linestring)"
            for i in range(1, 6))
        joins = " ".join(
            f"LEFT JOIN route_geom g{i} ON g{i}.id = tr.step{i}_geom_id"
            for i in range(1, 6))
        return (f"SELECT tr.rank, tr.total_time_min, tr.bus_cnt, tr.subway_cnt, {step_sel} "
                f"FROM transit_routes tr {joins} "
                f"WHERE tr.origin_cell=? AND tr.wp_id=? ORDER BY tr.rank")
    step_sel = ", ".join(
        f"step{i}_type, step{i}_time_min, step{i}_dist_m, "
        f"step{i}_노선, step{i}_출발, step{i}_도착, step{i}_linestring"
        for i in range(1, 6))
    return (f"SELECT rank, total_time_min, bus_cnt, subway_cnt, {step_sel} "
            f"FROM transit_routes WHERE origin_cell=? AND wp_id=? ORDER BY rank")


# ── GET /api/apt/{apt_seq}/routes ────────────────────────────
@router.get("/apt/{apt_seq}/routes")
def apt_routes(apt_seq: str, wp_id: int, response: Response, conn=Depends(get_db)):
    """단지 상세 — 모든 경로 옵션 (rank 1~N)"""
    import time
    timings = {}
    t0 = time.time()
    # 뷰(v_apt_transit_options)는 SQLite 쿼리 플래너가 apt_seq 조건을 뷰 안으로 밀어넣지 못해
    # 전체 스캔 → 7초 소요. 2단계 조회(grid_key 먼저 → transit_routes 직접)로 0.001초로 단축.
    gk_row = conn.execute(
        "SELECT grid_key FROM apartments WHERE apt_seq=?", [apt_seq]
    ).fetchone()
    timings['grid_key'] = round((time.time()-t0)*1000)
    if not gk_row or not gk_row['grid_key']:
        return {'apt_seq': apt_seq, 'wp_id': wp_id, 'options': []}

    rows = conn.execute(
        _routes_query(conn), [gk_row['grid_key'], wp_id]
    ).fetchall()
    timings['routes_q'] = round((time.time()-t0)*1000)

    options = []
    for r in rows:
        steps = []
        for i in range(5):
            off = 4 + i*7   # 각 step당 7개 컬럼 (type, time_min, dist_m, 노선, 출발, 도착, linestring)
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
                'linestring': r[off+6],   # 경로 폴리라인 (baked)
            })
        options.append({
            'rank': r['rank'],
            'total_time_min': r['total_time_min'],
            'bus_cnt': r['bus_cnt'],
            'subway_cnt': r['subway_cnt'],
            'steps': steps,
        })
    timings['TOTAL'] = round((time.time()-t0)*1000)
    print(f'[routes {apt_seq} wp{wp_id}] timings(ms): {timings} opts={len(options)}')
    response.headers['Server-Timing'] = ', '.join(
        f'{k};dur={v}' for k, v in timings.items())
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
async def apt_detail(apt_seq: str, wp_id: int, response: Response):
    """
    상세 패널용 — 거래내역 + POI + 시세차트 데이터
    통근경로는 /routes 엔드포인트를 별도 호출

    쿼리 7개 병렬화: apt(umd_nm 의존) 먼저 1회, 나머지 6개를 asyncio.gather로
    동시 실행. 각 쿼리는 풀에서 커넥션을 빌려 독립 스레드에서 돈다.
    (Tokyo 시절 순차 ~480ms → 병렬 ~2회 왕복으로 단축)

    구간별 계측: 각 쿼리의 '커넥션 획득(_conn)'과 '총 소요'를 분리 측정해
    timings에 기록하고, Server-Timing 응답 헤더로 노출한다(브라우저 DevTools →
    Network → detail 요청 → Timing 에서 구간별 ms 확인 가능).
    """
    import time
    import threading
    timings = {}
    _tlock = threading.Lock()
    t0 = time.time()
    threshold_year = year_minus(3)  # 3년 전 YYYY

    # 쿼리 1건을 돌리며 커넥션 획득 시간과 총 소요를 분리 계측하는 헬퍼.
    # body(conn)을 호출하고 timings[name]=총ms, timings[name+'_conn']=커넥션ms 기록.
    def _run(name, body):
        _ta = time.time()
        c = db_connect()
        _conn_ms = round((time.time() - _ta) * 1000)
        try:
            return body(c)
        finally:
            c.close()
            with _tlock:
                timings[name] = round((time.time() - _ta) * 1000)
                timings[name + '_conn'] = _conn_ms

    # ── Phase 1: 기본 단지 정보 (umd_nm 확보 + early return) ──────
    apt = await asyncio.to_thread(_run, 'apt', lambda c: c.execute("""
        SELECT a.apt_nm, a.umd_nm, a."kaptAddr", a.kaptdaCnt, a.lat, a.lng,
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
    """, [apt_seq]).fetchone())
    timings['phase1'] = round((time.time()-t0)*1000)
    if not apt:
        print(f'[detail {apt_seq}] 단지 없음 — timings: {timings}')
        return {}
    umd_nm = apt['umd_nm']

    # ── Phase 2: 나머지 8개 쿼리 병렬 (각자 풀 커넥션) ────────────
    def _b_fc(c):
        return c.execute(
            'SELECT pyeong_type, comment FROM apt_pt_friend_comment '
            'WHERE apt_seq=? AND wp_id=? ORDER BY LENGTH(comment) DESC',
            [apt_seq, wp_id]
        ).fetchall()

    def _b_tabs(c):
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

    def _b_chart(c):
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

    def _b_dong(c):
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

    def _b_trades(c):
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

    def _b_poi(c):
        return c.execute("""
            SELECT poi_lclas_cd, poi_mlsfc_cd, poi_nm, distance_m, walking_min
            FROM apt_walking_poi
            WHERE kaptCode = (
                SELECT kaptCode FROM apartments WHERE apt_seq = ? LIMIT 1
            )
              AND walking_min <= ?
            ORDER BY distance_m
            LIMIT 90
        """, [apt_seq, cfg.POI_WALK_MAX_MIN]).fetchall()

    # spec-43: slope·building_register를 독립 커넥션으로 진짜 병렬화. 누락 테이블은 무해 처리.
    def _b_slope(c):
        try:
            return c.execute(
                'SELECT apt_slope_avg FROM apt_slope WHERE kaptCode = '
                '(SELECT kaptCode FROM apartments WHERE apt_seq = ? LIMIT 1)',
                [apt_seq]
            ).fetchone()
        except Exception:
            return None

    def _b_br(c):
        try:
            return c.execute(
                'SELECT vlRat, bcRat, strctCdNm, useAprDay FROM building_register '
                'WHERE kaptCode = '
                '(SELECT kaptCode FROM apartments WHERE apt_seq = ? LIMIT 1)',
                [apt_seq]
            ).fetchall()
        except Exception:
            return []

    # dong(동) 평균은 umd_nm 단위로 동일 → 같은 동의 모든 단지가 같은 결과.
    # 캐시 적중 시 무거운 교차 스캔 쿼리와 커넥션 획득을 둘 다 생략한다.
    _dong_key = (umd_nm, threshold_year)
    _dh = _DONG_CACHE.get(_dong_key)
    dong_cached = _dh[1] if (_dh and time.time() - _dh[0] < _DONG_TTL) else None

    tasks = [
        asyncio.to_thread(_run, 'fc', _b_fc),
        asyncio.to_thread(_run, 'tabs', _b_tabs),
        asyncio.to_thread(_run, 'chart', _b_chart),
        asyncio.to_thread(_run, 'trades', _b_trades),
        asyncio.to_thread(_run, 'poi', _b_poi),
        asyncio.to_thread(_run, 'slope', _b_slope),
        asyncio.to_thread(_run, 'br', _b_br),
    ]
    if dong_cached is None:
        tasks.append(asyncio.to_thread(_run, 'dong', _b_dong))

    results = await asyncio.gather(*tasks)
    (fc_rows, pyeong_tabs, chart_rows, trade_rows, poi_rows,
     slope_row, br_rows) = results[:7]
    if dong_cached is None:
        dong_avg_rows = results[7]
        # 캐시 채우기 (쓰기는 메인 코루틴에서만 → 스레드 경쟁 없음). 무한 증가 방지 캡.
        if len(_DONG_CACHE) > 500:
            _DONG_CACHE.clear()
        _DONG_CACHE[_dong_key] = (time.time(), dong_avg_rows)
    else:
        dong_avg_rows = dong_cached
        timings['dong'] = 0  # 캐시 적중(쿼리·커넥션 생략)

    infra = (slope_row, br_rows)
    timings['dong_cache'] = 1 if dong_cached is not None else 0
    timings['parallel_8q'] = round((time.time()-t0)*1000)

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
    if SLOPE_LABEL_ENABLED and slope_row and slope_row['apt_slope_avg'] is not None:
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
    # 브라우저 DevTools에서 구간별 ms 확인용 (Network → 요청 → Timing/Headers)
    response.headers['Server-Timing'] = ', '.join(
        f'{k};dur={v}' for k, v in timings.items())

    kapt_addr = apt.get('kaptAddr', '') or ''
    gu_nm = next((t for t in kapt_addr.split() if t.endswith('구')), '')

    return {
        'apt_seq':   apt_seq,
        'apt_nm':    apt['apt_nm'],
        'umd_nm':    umd_nm,
        'gu_nm':     gu_nm,
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
