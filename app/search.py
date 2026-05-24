"""
검색 API 라우터

POST /api/search        : 직장 + 조건 → 카드 리스트 (LLM 친구 한 마디 포함)
GET  /api/apt/{seq}/routes : 단지 상세 경로 옵션 (rank 1~N)
"""
import asyncio
import re
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field, field_validator
from app.db import get_db, connect as db_connect
from app.workplaces import get_or_create
from app.transit import fetch_cells, haversine, cell_center
from app.ai import build_recommendations, build_stats, build_comments, card_key
from app.portable import upsert_sql, year_month_minus, year_minus

router = APIRouter()


# ── 요청 스키마 ──────────────────────────────────────────────
_ALLOWED_PYEONG = {'10평미만', '10평대', '20평대', '30평대', '40평대', '50평대+'}

class SearchRequest(BaseModel):
    workplace_address: str = Field(..., min_length=2, max_length=200, description="직장 도로명/지번 주소")
    max_minutes:  int = Field(60, ge=10, le=60, description="사용자 선택값. 내부적으로 10분 여유 차감")
    max_price:    int = Field(50000, ge=1000, le=2_000_000, description="만원 단위, 예: 50000=5억")
    pyeong_types: list[str] = Field(default_factory=lambda: ['10평대','20평대'], min_length=1, max_length=6)
    min_kaptdaCnt: int | None = Field(None, ge=0, le=100_000, description="최소 단지 세대수 (선택). 미지정=100")

    @field_validator('pyeong_types')
    @classmethod
    def _check_pyeong_types(cls, v: list[str]) -> list[str]:
        invalid = [p for p in v if p not in _ALLOWED_PYEONG]
        if invalid:
            raise ValueError(f'허용되지 않는 평형: {invalid}')
        return v

# 통근시간 여유분 (사용자 선택값에서 차감)
# 10→15: 60분 입력 시 effective 45분, 반경 16.7→15km, 셀 ~19%↓
COMMUTE_BUFFER_MIN = 15

# Vercel Hobby maxDuration 60s 안에 끝내기 위한 ODsay 호출 셀 상한.
# 신규 워크플레이스 첫 검색에서 초과분은 다음 검색에 캐시 채워짐 (자연 점진 완성).
# 4키 × 4동시 × ~1.2s/round × 100ms sleep → ~250셀이 ~25s 안에 처리됨.
MAX_FETCH_CELLS_PER_CALL = 250


# ── POST /api/search ─────────────────────────────────────────
@router.post("/search")
async def search(req: SearchRequest, background_tasks: BackgroundTasks, conn=Depends(get_db)):
    # ─ 1. workplace 등록 / wp_id 확보 ─
    # get_or_create 안의 Kakao HTTP 호출이 동기 블로킹이므로 to_thread로 오프로드
    wp = await asyncio.to_thread(get_or_create, conn, req.workplace_address)
    if not wp:
        raise HTTPException(400, f'주소 변환 실패: {req.workplace_address}')

    wp_id = wp['wp_id']
    dest_lat, dest_lng = wp['lat'], wp['lng']
    # 통근시간 여유분 차감: 사용자 60분 입력 → 실제 50분 이내 매물만
    effective_max_min = max(req.max_minutes - COMMUTE_BUFFER_MIN, 5)
    radius_km = effective_max_min * 20 / 60

    # ─ 2. 후보 단지 → 셀 ─
    apt_filter = 'WHERE is_apt=1 AND recent_trade=3'
    apt_params = []
    if req.min_kaptdaCnt is not None:
        apt_filter += ' AND kaptdaCnt >= ?'
        apt_params.append(req.min_kaptdaCnt)
    apts = conn.execute(
        f'SELECT apt_seq, lat, lng FROM apartments {apt_filter}', apt_params
    ).fetchall()
    near_keys = [a['apt_seq'] for a in apts
                 if haversine(a['lat'], a['lng'], dest_lat, dest_lng) <= radius_km]

    if not near_keys:
        return _empty_response(wp, [])

    ph = ','.join('?'*len(near_keys))
    pt = ','.join('?'*len(req.pyeong_types))
    matched_rows = conn.execute(
        f'SELECT DISTINCT apt_seq FROM trade_recent '
        f'WHERE apt_seq IN ({ph}) AND pyeong_type IN ({pt}) AND deal_amount_int<=?',
        near_keys + req.pyeong_types + [req.max_price]
    ).fetchall()
    matched_keys = [r['apt_seq'] for r in matched_rows]

    if not matched_keys:
        return _empty_response(wp, [])

    ph2 = ','.join('?'*len(matched_keys))
    cells = sorted(set(r['grid_key'] for r in conn.execute(
        f'SELECT DISTINCT grid_key FROM apartments WHERE apt_seq IN ({ph2})',
        matched_keys
    ).fetchall()))

    # ─ 3. 캐시 미스 셀만 ODsay 호출 ─
    # passed_filter=1 인 셀만 "캐시됨"으로 간주 → passed_filter=0/응답실패는 재호출
    # (ApiKey 인증 실패한 키가 섞여 있던 시기에 만들어진 빈 캐시 자동 복구)
    cached = set(r['origin_cell'] for r in conn.execute(
        'SELECT origin_cell FROM transit_cache WHERE wp_id=? AND passed_filter=1', (wp_id,)
    ).fetchall())
    conn.execute('DELETE FROM transit_cache WHERE wp_id=? AND passed_filter=0', (wp_id,))
    conn.commit()
    to_fetch_all = [c for c in cells if c not in cached]

    # 직장 가까운 셀부터 N개만 처리 (60s 안에 끝내기).
    # 남은 셀은 다음 검색에서 캐시 채워짐.
    def _cell_dist(c):
        clat, clng = cell_center(c)
        return haversine(clat, clng, dest_lat, dest_lng)
    to_fetch_sorted = sorted(to_fetch_all, key=_cell_dist)
    to_fetch = to_fetch_sorted[:MAX_FETCH_CELLS_PER_CALL]
    deferred_cells = len(to_fetch_all) - len(to_fetch)

    odsay_stats = await fetch_cells(conn, wp, to_fetch)

    # ─ 4. 카드 쿼리 (인덱스 최적화된 단일 쿼리) ─
    min_cnt_clause = ' AND a.kaptdaCnt >= ?' if req.min_kaptdaCnt is not None else ''
    cards_params = [wp_id, effective_max_min, req.max_price, *req.pyeong_types]
    if req.min_kaptdaCnt is not None:
        cards_params.append(req.min_kaptdaCnt)

    # 카드 = (apt_seq, pyeong_type) 단위. 평형별로 행 1개씩.
    cards = conn.execute(f"""
        SELECT
            a.apt_seq, a.apt_nm, a.umd_nm, a.kaptdaCnt, a.lat, a.lng,
            a.kaptCode,
            r.total_time_min, r.bus_cnt, r.subway_cnt,
            r.step1_type, r.step1_time_min, r.step1_노선,
            r.step2_type, r.step2_time_min, r.step2_노선,
            r.step3_type, r.step3_time_min, r.step3_노선,
            r.step4_type, r.step4_time_min, r.step4_노선,
            r.step5_type, r.step5_time_min, r.step5_노선,
            t.pyeong_type,
            MIN(t.deal_amount_int) AS price_low,
            MAX(t.deal_amount_int) AS price_high,
            COUNT(t.id) AS deal_count,
            AVG(t.deal_amount_int * 1.0 / NULLIF(t.pyeong, 0)) AS pyeong_price_avg,
            MAX(k.kaptTopFloor) AS top_floor,
            MAX(k.kaptUsedate) AS use_date
        FROM apartments a
        LEFT JOIN kapt_complexes k ON a.kaptCode = k.kaptCode
        JOIN transit_routes r ON a.grid_key = r.origin_cell
        JOIN trade_recent t   ON a.apt_seq  = t.apt_seq
        WHERE a.is_apt=1
          AND r.wp_id=? AND r.rank=1 AND r.total_time_min<=?
          AND t.deal_amount_int<=?
          AND t.pyeong_type IN ({pt})
          {min_cnt_clause}
        GROUP BY
            a.apt_seq, a.apt_nm, a.umd_nm, a.kaptdaCnt, a.lat, a.lng,
            a.kaptCode,
            r.total_time_min, r.bus_cnt, r.subway_cnt,
            r.step1_type, r.step1_time_min, r.step1_노선,
            r.step2_type, r.step2_time_min, r.step2_노선,
            r.step3_type, r.step3_time_min, r.step3_노선,
            r.step4_type, r.step4_time_min, r.step4_노선,
            r.step5_type, r.step5_time_min, r.step5_노선,
            t.pyeong_type
        ORDER BY r.total_time_min, price_low
    """, cards_params).fetchall()

    # ─ 4b. 카드별 최근 거래 (3개월, 최대 4건) ─
    # 카드 단위 = (apt_seq, pyeong_type) 이므로 recent_map 키도 동일하게.
    if cards:
        seqs = list({c['apt_seq'] for c in cards})
        ph = ','.join('?' * len(seqs))
        threshold_ym = year_month_minus(3)  # 3개월 전 YYYY*100+MM
        # ROW_NUMBER()로 DB에서 최대 4건만 가져옴 (전체 fetchall 후 Python 필터 방식 대비
        # 대형 단지/활발한 지역에서 수만 행 전송을 방지)
        recent_rows = conn.execute(f"""
            WITH ranked AS (
                SELECT apt_seq, pyeong, pyeong_type, floor, deal_amount_int,
                       deal_year, deal_month, deal_day, dealing_gbn,
                       ROW_NUMBER() OVER (
                           PARTITION BY apt_seq, pyeong_type
                           ORDER BY deal_year DESC, deal_month DESC, deal_day DESC
                       ) AS rn
                FROM trade_recent
                WHERE apt_seq IN ({ph})
                  AND deal_year*100 + deal_month >= ?
            )
            SELECT apt_seq, pyeong, pyeong_type, floor, deal_amount_int,
                   deal_year, deal_month, deal_day, dealing_gbn
            FROM ranked WHERE rn <= 4
            ORDER BY apt_seq, pyeong_type,
                     deal_year DESC, deal_month DESC, deal_day DESC
        """, seqs + [threshold_ym]).fetchall()
        recent_map: dict = {}
        for row in recent_rows:
            key = (row['apt_seq'], row['pyeong_type'])
            recent_map.setdefault(key, []).append({
                'pyeong': row['pyeong'],
                'floor': row['floor'],
                'amount': row['deal_amount_int'],
                'date': f"{row['deal_year'] % 100:02d}.{row['deal_month']:02d}.{row['deal_day']:02d}",
                'gbn': row['dealing_gbn'],
            })
    else:
        recent_map = {}

    # ─ 5. 카드 변환 + 추천 로직 (통근버킷 × 평형 매트릭스) ─
    raw_cards = [_card_to_dict(c, recent_map) for c in cards]
    rec = build_recommendations(raw_cards, effective_max_min)
    buckets = rec['buckets']
    all_cards = rec['cards']

    # ─ 6. 통계 계산 ─
    stats = build_stats(all_cards, buckets)

    # ─ 7. LLM 친구 한 마디 — 전체 카드 (추천=Sonnet 긴 코멘트 / 일반=Haiku 한 줄) ─
    cached_comments: dict[str, str] = {}  # card_key → comment
    if all_cards:
        # wp_id 단위로 모든 캐시 조회 (카드 수 많아도 단일 쿼리)
        rows = conn.execute(
            'SELECT apt_seq, pyeong_type, comment FROM apt_pt_friend_comment '
            'WHERE wp_id=?',
            [wp_id],
        ).fetchall()
        for row in rows:
            cached_comments[f"{row['apt_seq']}:{row['pyeong_type']}"] = row['comment']

    miss_cards = [c for c in all_cards if card_key(c) not in cached_comments]
    llm_pending = len(miss_cards) > 0
    if miss_cards:
        wp_label = wp.get('address_norm') or wp.get('address_input', '')
        background_tasks.add_task(_generate_comments_bg, miss_cards, all_cards, wp_id, wp_label)

    # 카드에 코멘트 병합 (캐시된 것만 즉시 표시)
    for c in all_cards:
        c['friend_comment'] = cached_comments.get(card_key(c), '')

    return {
        'wp_id': wp_id,
        'llm_pending': llm_pending,
        'workplace': {
            'address_input': wp['address_input'],
            'address_norm':  wp['address_norm'],
            'lat': wp['lat'], 'lng': wp['lng'],
        },
        'stats': stats,
        'buckets': buckets,
        'cards': all_cards,
        'meta': {
            'odsay_calls_made': odsay_stats['fetched'],
            'odsay_passed':     odsay_stats['passed'],
            'odsay_failed':     odsay_stats['failed'],
            'cache_hits':       len(cached),
            'odsay_elapsed_ms': odsay_stats['elapsed_ms'],
            'llm_cached':       len(cached_comments),
            'llm_pending':      len(miss_cards),
            'llm_pending_recommend': sum(1 for c in miss_cards if c.get('is_recommended')),
            'llm_pending_regular':   sum(1 for c in miss_cards if not c.get('is_recommended')),
            # 신규 워크플레이스 첫 검색에선 일부 셀이 다음 검색으로 미뤄짐.
            # partial=True 면 프론트가 잠시 후 재검색해서 결과 보강 가능.
            'partial':          deferred_cells > 0,
            'deferred_cells':   deferred_cells,
            'total_cells':      len(cells),
        },
    }


# ── 백그라운드: LLM 코멘트 생성 + DB 캐싱 ───────────────────
async def _generate_comments_bg(miss_cards: list, all_cards: list, wp_id: int, wp_label: str):
    """BackgroundTask — 응답 후 실행. 별도 DB 커넥션 사용.

    miss_cards: 코멘트 생성 대상 (추천 카드 중 캐시 미스)
    all_cards : 전체 카드 (평형별 평균가 등 컨텍스트 계산용)
    """
    import time, traceback
    t0 = time.time()
    rec_n = sum(1 for c in miss_cards if c.get('is_recommended'))
    reg_n = len(miss_cards) - rec_n
    print(f'[bg_comments] 시작 — 추천 {rec_n}개, 일반 {reg_n}개')
    try:
        new_comments = await build_comments(miss_cards, all_cards, wp_label)
        ok_n = sum(1 for v in new_comments.values()
                   if v.get('comment') and not v['comment'].startswith('('))
        print(f'[bg_comments] LLM 완료 ({time.time()-t0:.1f}s): {ok_n}/{len(new_comments)} 성공')
    except Exception as e:
        print(f'[bg_comments] LLM 호출 자체 실패: {type(e).__name__}: {e}')
        print(traceback.format_exc())
        return

    # DB 저장 (실패 코멘트도 저장하면 다음에 또 시도 안 함 → 성공한 것만 저장)
    try:
        conn = db_connect()
        try:
            rows = []
            for c in miss_cards:
                ck = card_key(c)
                comment = new_comments.get(ck, {}).get('comment', '')
                # '(생성 실패)' 같은 에러 메시지는 캐시하지 않음 → 다음 검색 때 재시도
                if comment and not comment.startswith('('):
                    rows.append((c['apt_seq'], c['pyeong_type'], wp_id, comment))
            if rows:
                conn.executemany(
                    upsert_sql(
                        'apt_pt_friend_comment',
                        ['apt_seq', 'pyeong_type', 'wp_id', 'comment'],
                        pk_cols=['apt_seq', 'pyeong_type', 'wp_id'],
                    ),
                    rows,
                )
                conn.commit()
                print(f'[bg_comments] DB 저장 완료 — {len(rows)}건')
        finally:
            conn.close()
    except Exception as e:
        print(f'[bg_comments] DB 저장 실패: {type(e).__name__}: {e}')
        print(traceback.format_exc())


# ── GET /api/comments — 생성된 댓글 폴링용 ──────────────────
@router.get("/comments")
def get_comments(wp_id: int, keys: str, conn=Depends(get_db)):
    """LLM 백그라운드 완료 후 프론트가 폴링하는 경량 엔드포인트.

    keys: "apt_seq:pyeong_type,apt_seq:pyeong_type,..." 형식
    반환: {"apt_seq:pyeong_type": {"comment": "..."}}
    """
    pairs = []
    for k in keys.split(','):
        k = k.strip()
        if ':' not in k:
            continue
        seq, pt = k.split(':', 1)
        pairs.append((seq.strip(), pt.strip()))
    if not pairs:
        return {}
    if len(pairs) > 200:
        raise HTTPException(400, 'keys 개수가 200을 초과할 수 없습니다')
    conds = ' OR '.join(['(apt_seq=? AND pyeong_type=?)'] * len(pairs))
    params = [wp_id]
    for s, p in pairs:
        params.extend([s, p])
    rows = conn.execute(
        f'SELECT apt_seq, pyeong_type, comment FROM apt_pt_friend_comment '
        f"WHERE wp_id=? AND ({conds}) AND comment != ''",
        params,
    ).fetchall()
    return {
        f"{r['apt_seq']}:{r['pyeong_type']}": {'comment': r['comment']}
        for r in rows
    }


def _empty_response(wp, _cards):
    return {
        'wp_id': wp['wp_id'],
        'llm_pending': False,
        'workplace': {
            'address_input': wp['address_input'],
            'address_norm':  wp['address_norm'],
            'lat': wp['lat'], 'lng': wp['lng'],
        },
        'stats': {'total': 0},
        'buckets': [],
        'cards': [],
        'meta': {},
    }


def _card_to_dict(r, recent_map: dict | None = None):
    bc, sc = r['bus_cnt'], r['subway_cnt']

    # 대중교통 요약 (지하철 호선 + 환승 + 도보)
    steps = []
    for i in range(1, 6):
        st = r[f'step{i}_type']
        if not st:
            break
        steps.append({
            'type': st,
            'time': r[f'step{i}_time_min'],
            'line': r[f'step{i}_노선'],
        })

    walk_min = None
    subway_line = None
    for s in steps:
        if s['type'] in ('도보', '환승도보', 'WALK') and walk_min is None:
            walk_min = s['time']
        if s['type'] in ('지하철', 'SUBWAY') and subway_line is None:
            # "수도권 4호선" → "4호선"
            line_raw = s['line'] or ''
            m = re.search(r'\d+호선', line_raw)
            subway_line = m.group(0) if m else (line_raw.strip() or None)

    if subway_line:
        xfer = max(sc - 1, 0)
        if xfer == 0:
            transit_summary = f'{subway_line} 직통'
        else:
            transit_summary = f'{subway_line} {xfer}회환승'
        if walk_min:
            transit_summary += f' (도보 {walk_min}분)'
    elif bc:
        xfer = max(bc - 1, 0)
        transit_summary = '버스 직통' if xfer == 0 else f'버스 {xfer}회환승'
        if walk_min:
            transit_summary += f' (도보 {walk_min}분)'
    else:
        transit_summary = f'{r["total_time_min"]}분'

    # 준공연도: kaptUsedate = "20040517" → 2004
    use_date = r['use_date'] or ''
    build_year = int(use_date[:4]) if len(use_date) >= 4 and use_date[:4].isdigit() else None

    apt_seq = r['apt_seq']
    pyeong_type = r['pyeong_type'] if 'pyeong_type' in r.keys() else None
    # 평당가 (만원/평)
    try:
        pa = r['pyeong_price_avg']
        pyeong_price = int(pa) if pa else None
    except (IndexError, KeyError):
        pyeong_price = None
    return {
        'apt_seq': apt_seq, 'apt_nm': r['apt_nm'], 'umd_nm': r['umd_nm'],
        'pyeong_type': pyeong_type,
        'kaptdaCnt': int(r['kaptdaCnt'] or 0),
        'top_floor': r['top_floor'],
        'build_year': build_year,
        'lat': r['lat'], 'lng': r['lng'],
        'total_time_min': r['total_time_min'],
        'bus_cnt': bc, 'subway_cnt': sc,
        'transit_summary': transit_summary,
        'price_low':  r['price_low'], 'price_high': r['price_high'],
        'pyeong_price_avg': pyeong_price,
        'deal_count': r['deal_count'],
        'recent_trades': (recent_map or {}).get((apt_seq, pyeong_type), []),
    }


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
            if not t: continue
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


# ── GET /api/apt/{apt_seq}/detail ────────────────────────────
@router.get("/apt/{apt_seq}/detail")
def apt_detail(apt_seq: str, wp_id: int, conn=Depends(get_db)):
    """
    상세 패널용 — 거래내역 + POI + 시세차트 데이터
    통근경로는 /routes 엔드포인트를 별도 호출
    """
    import time
    timings = {}
    t0 = time.time()

    # ── 기본 단지 정보 + 건물 상세 ────────────────────────────────
    apt = conn.execute("""
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
    timings['apt_info'] = round((time.time()-t0)*1000)
    if not apt:
        print(f'[detail {apt_seq}] 단지 없음 — timings: {timings}')
        return {}

    # 주차대수: kaptdPcnt(지하) + kaptdPcntu(지상)
    def _to_int(v):
        try: return int(v or 0)
        except: return 0
    parking_underground = _to_int(apt['kaptdCccnt'])
    parking_ground = _to_int(apt['kaptdPcntu'])
    parking_total = parking_underground + parking_ground if (parking_underground or parking_ground) else None

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

    umd_nm = apt['umd_nm']

    # ── 친구 한 마디 (새 테이블 = 평형별 분리) ──────────────────
    # detail 화면은 단지 통합이라 가장 긴 코멘트(=추천 카드의 Sonnet) 우선 표시
    fc_rows = conn.execute(
        'SELECT pyeong_type, comment FROM apt_pt_friend_comment '
        'WHERE apt_seq=? AND wp_id=? ORDER BY LENGTH(comment) DESC',
        [apt_seq, wp_id]
    ).fetchall()
    friend_comment = fc_rows[0]['comment'] if fc_rows else None
    tier = None  # 신규 컨셉엔 tier 없음
    timings['comment'] = round((time.time()-t0)*1000)

    # ── 평수 탭 목록 (거래 많은 순, 디폴트=1위) ─────────────────
    t1 = time.time()
    threshold_year = year_minus(3)  # 3년 전 YYYY
    pyeong_tabs = conn.execute("""
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
    timings['pyeong_tabs'] = round((time.time()-t1)*1000); t1 = time.time()

    # ── 시세 차트 — 단지 월별 평균 (3년치, 평수별 전체금액) ──────
    # ym 문자열은 SELECT 시 deal_year/deal_month만 가져와서 Python에서 포맷
    # (printf는 SQLite 전용, Postgres는 LPAD — portable subset에서 빠짐)
    chart_rows = conn.execute("""
        SELECT pyeong_type, pyeong, deal_year, deal_month,
               ROUND(AVG(deal_amount_int)) AS avg_amount,
               COUNT(*) AS cnt
        FROM trade_history
        WHERE apt_seq = ?
          AND deal_year >= ?
        GROUP BY pyeong_type, pyeong, deal_year, deal_month
        ORDER BY pyeong_type, deal_year, deal_month
    """, [apt_seq, threshold_year]).fetchall()

    # 동 평균 — trade_history.umd_nm 직접 사용 (JOIN 없이 idx_th_umd_py_ym 활용)
    dong_avg_rows = conn.execute("""
        SELECT pyeong_type, deal_year, deal_month,
               ROUND(AVG(deal_amount_int)) AS avg_amount,
               COUNT(*) AS cnt
        FROM trade_history
        WHERE umd_nm = ?
          AND deal_year >= ?
        GROUP BY pyeong_type, deal_year, deal_month
        ORDER BY pyeong_type, deal_year, deal_month
    """, [umd_nm, threshold_year]).fetchall()
    timings['chart_rows+dong_avg'] = round((time.time()-t1)*1000); t1 = time.time()

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

    # ── 최근 실거래 내역 (최근 20건) ──────────────────────────
    trade_rows = conn.execute("""
        SELECT deal_year, deal_month, deal_day,
               pyeong, pyeong_type, deal_amount_int, floor
        FROM trade_history
        WHERE apt_seq = ?
        ORDER BY deal_year DESC, deal_month DESC, deal_day DESC
        LIMIT 20
    """, [apt_seq]).fetchall()

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
    timings['trades'] = round((time.time()-t1)*1000); t1 = time.time()

    # ── 도보 POI ───────────────────────────────────────────────
    poi_rows = conn.execute("""
        SELECT poi_lclas_cd, poi_mlsfc_cd, poi_nm, distance_m, walking_min
        FROM apt_walking_poi
        WHERE kaptCode = (
            SELECT kaptCode FROM apartments WHERE apt_seq = ? LIMIT 1
        )
        ORDER BY distance_m
        LIMIT 30
    """, [apt_seq]).fetchall()

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
        vs_dong_pct  = round((apt_recent - dong_recent) / dong_recent * 100, 1) \
                       if (apt_recent and dong_recent) else None
        vs_dong_diff = int(apt_recent - dong_recent) \
                       if (apt_recent and dong_recent) else None

        price_summary = {
            'pyeong_type': top_pyeong_type,
            'pyeong': top_pyeong,
            'change_6m_pct': chg_pct,
            'vs_dong_pct':   vs_dong_pct,
            'vs_dong_diff':  vs_dong_diff,
        }

    timings['poi+summary'] = round((time.time()-t1)*1000)
    timings['TOTAL'] = round((time.time()-t0)*1000)
    print(f'[detail {apt_seq}] timings(ms): {timings}')

    return {
        'apt_seq':   apt_seq,
        'apt_nm':    apt['apt_nm'],
        'umd_nm':    umd_nm,
        'kaptdaCnt': apt['kaptdaCnt'],
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
