"""
검색 API 라우터

POST /api/search        : 직장 + 조건 → 카드 리스트 (캐시된 친구 한 마디만 포함)
POST /api/comments/generate : 검색 결과 카드의 친구 한 마디 생성 트리거
GET  /api/apt/{seq}/routes : 단지 상세 경로 옵션 (rank 1~N)
"""
import asyncio
import time
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks

# Vercel 서버리스: 응답 후 함수가 동결/종료되어 create_task가 죽음 →
# BackgroundTasks(응답 사이클 내 await)로 생존 보장. 로컬은 create_task로 분리.
from pydantic import BaseModel, Field, field_validator
from app.db import get_db, connect as db_connect
from app.workplaces import get_or_create
from app.transit import fetch_cells, haversine, cell_center
from app.ai import build_recommendations, build_stats, build_comments, card_key
from app.portable import upsert_sql, year_month_minus, greatest
from app.chat import router as chat_router
from app.detail import router as detail_router
from app.cards import _card_to_dict
from config import cfg

router = APIRouter()
# 분리된 서브 라우터를 같은 router에 합침 (main.py는 from app.search import router 그대로)
#   - chat.py   : /apt/{seq}/chat
#   - detail.py : /apt/{seq}/routes, /search/apt-lookup, /apt/{seq}/detail
router.include_router(chat_router)
router.include_router(detail_router)


# ── apartments 인메모리 캐시 ─────────────────────────────────────────
_apt_cache: dict = {'rows': None, 'ts': 0.0}

# 백그라운드 LLM 태스크 참조 보관 (GC로 중도 취소되는 것 방지)
_bg_tasks: set = set()

def _get_cached_apts(conn) -> list:
    """apartments 전체를 인메모리 캐싱. SELECT apt+grid_key DB 왕복 절감."""
    now = time.monotonic()
    if _apt_cache['rows'] is None or now - _apt_cache['ts'] > cfg.APT_CACHE_TTL_S:
        _apt_cache['rows'] = conn.execute(
            'SELECT apt_seq, lat, lng, grid_key, build_year, kaptdaCnt '
            'FROM apartments WHERE is_apt=1 AND recent_trade=3'
        ).fetchall()
        _apt_cache['ts'] = now
    return _apt_cache['rows']


# ── 요청 스키마 ──────────────────────────────────────────────
_ALLOWED_PYEONG = {'10평미만', '10평대', '20평대', '30평대', '40평대', '50평대+'}


class SearchRequest(BaseModel):
    workplace_address: str = Field(..., min_length=2, max_length=200, description="직장 도로명/지번 주소")
    workplace_address_2: str | None = Field(
        None, min_length=2, max_length=200,
        description="두 번째 직장 주소 (맞벌이용, 선택)",
    )
    max_minutes:  int = Field(60, ge=10, le=60, description="사용자 선택값. 내부적으로 10분 여유 차감")
    max_price:    int = Field(50000, ge=1000, le=2_000_000, description="만원 단위, 예: 50000=5억")
    pyeong_types: list[str] = Field(
        default_factory=lambda: ['10평대', '20평대'], min_length=1, max_length=6,
    )
    min_kaptdaCnt: int | None = Field(
        None, ge=0, le=100_000, description="최소 단지 세대수 (선택). 미지정=100",
    )
    build_year_min: int | None = Field(
        None, ge=1960, le=2030, description="최소 준공연도 (예: 2010 → 2010년 이후 준공 단지만)",
    )
    min_price: int | None = Field(
        None, ge=1000, le=2_000_000,
        description="최소 가격 (만원). 예: 30000=3억. 미지정=하한 없음.",
    )

    @field_validator('workplace_address_2')
    @classmethod
    def _check_workplace_2(cls, v, info):
        if v is not None:
            wp1 = info.data.get('workplace_address', '').strip()
            if v.strip() == wp1:
                raise ValueError('두 직장이 동일합니다. 단일 모드로 검색하세요.')
        return v

    @field_validator('min_price')
    @classmethod
    def _check_min_price(cls, v, info):
        if v is not None:
            max_p = info.data.get('max_price')
            if max_p is not None and v >= max_p:
                raise ValueError('min_price는 max_price보다 작아야 합니다')
        return v

    @field_validator('pyeong_types')
    @classmethod
    def _check_pyeong_types(cls, v: list[str]) -> list[str]:
        invalid = [p for p in v if p not in _ALLOWED_PYEONG]
        if invalid:
            raise ValueError(f'허용되지 않는 평형: {invalid}')
        return v


class CommentGenerateRequest(BaseModel):
    wp_id: int = Field(..., ge=1)
    wp_label: str | None = Field(None, max_length=200)
    cards: list[dict] = Field(default_factory=list, max_length=200)


# 검색 정책 상수 — config.py(cfg)에서 중앙 관리, 여기선 로컬 alias만 유지
# (변경 시 .env 또는 Vercel 대시보드에서 override)
COMMUTE_BUFFER_MIN       = cfg.COMMUTE_BUFFER_MIN
MAX_FETCH_CELLS_PER_CALL = cfg.MAX_FETCH_CELLS
ODSAY_HARD_TIMEOUT_S     = cfg.ODSAY_HARD_TIMEOUT_S
WALL_CLOCK_BUDGET_S      = cfg.WALL_CLOCK_BUDGET_S


async def _fetch_card_extras(seqs: list, wp_id: int, threshold_ym: int, ym_3mo: int, ym_9mo: int):
    """recent_rows / tag_rows / chg_rows / comment_cache 를 asyncio.gather로 병렬 조회."""
    ph = ','.join('?' * len(seqs))

    def _recent():
        c = db_connect()
        try:
            return c.execute(f"""
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
                      AND dealing_gbn = '중개거래'
                )
                SELECT apt_seq, pyeong, pyeong_type, floor, deal_amount_int,
                       deal_year, deal_month, deal_day, dealing_gbn
                FROM ranked WHERE rn <= 4
                ORDER BY apt_seq, pyeong_type,
                         deal_year DESC, deal_month DESC, deal_day DESC
            """, seqs + [threshold_ym]).fetchall()
        finally:
            c.close()

    def _tags():
        c = db_connect()
        try:
            return c.execute(
                f'SELECT apt_seq, pyeong_type, tag_type, label, detail '
                f'FROM trade_tags WHERE apt_seq IN ({ph})',
                seqs,
            ).fetchall()
        except Exception:
            return []
        finally:
            c.close()

    def _chg():
        c = db_connect()
        try:
            return c.execute(
                f'SELECT apt_seq, pyeong_type,'
                f'  AVG(CASE WHEN deal_year*100+deal_month >= {ym_3mo}'
                f'           THEN deal_amount_int END) AS recent_avg,'
                f'  AVG(CASE WHEN deal_year*100+deal_month >= {ym_9mo}'
                f'            AND deal_year*100+deal_month < {ym_3mo}'
                f'           THEN deal_amount_int END) AS past_avg'
                f' FROM trade_history'
                f' WHERE apt_seq IN ({ph})'
                f'   AND deal_year*100+deal_month >= {ym_9mo}'
                f' GROUP BY apt_seq, pyeong_type',
                seqs,
            ).fetchall()
        except Exception:
            return []
        finally:
            c.close()

    def _comments():
        c = db_connect()
        try:
            return c.execute(
                'SELECT apt_seq, pyeong_type, comment FROM apt_pt_friend_comment WHERE wp_id=?',
                [wp_id],
            ).fetchall()
        finally:
            c.close()

    return await asyncio.gather(
        asyncio.to_thread(_recent),
        asyncio.to_thread(_tags),
        asyncio.to_thread(_chg),
        asyncio.to_thread(_comments),
    )


# ── POST /api/search ─────────────────────────────────────────
@router.post("/search")
async def search(req: SearchRequest, background_tasks: BackgroundTasks, conn=Depends(get_db)):
    import time as _time
    _t0 = _time.monotonic()   # 벽시계 타이머 시작 (Vercel 60s 예산 추적용)

    # ─ 1. workplace 등록 / wp_id 확보 ─
    # get_or_create 안의 Kakao HTTP 호출이 동기 블로킹이므로 to_thread로 오프로드
    wp = await asyncio.to_thread(get_or_create, conn, req.workplace_address)
    if not wp:
        raise HTTPException(400, f'주소 변환 실패: {req.workplace_address}')

    wp_id = wp['wp_id']
    dest_lat, dest_lng = wp['lat'], wp['lng']
    # 통근시간 여유분 차감: 사용자 60분 입력 → 실제 50분 이내 매물만.
    # 단, 최소 옵션(10분)은 차감하면 0/5분이 되어 의미가 없으므로 그대로 사용.
    if req.max_minutes <= 10:
        effective_max_min = req.max_minutes
    else:
        effective_max_min = max(req.max_minutes - COMMUTE_BUFFER_MIN, 5)
    radius_km = effective_max_min * cfg.AVG_SPEED_KMH / 60

    # ─ 1b. 두 번째 직장 (dual workplace 모드) ─
    wp_2 = None
    if req.workplace_address_2:
        wp_2 = await asyncio.to_thread(get_or_create, conn, req.workplace_address_2)
        if not wp_2:
            raise HTTPException(400, f'두 번째 주소 변환 실패: {req.workplace_address_2}')
        if wp_2['wp_id'] == wp['wp_id']:
            raise HTTPException(422, '두 직장이 동일합니다. 단일 모드로 검색하세요.')
    dual = wp_2 is not None
    wp_id_2 = wp_2['wp_id'] if dual else None

    # ─ 2. 후보 단지 → 셀 (인메모리 캐시, DB 왕복 2회 절감) ─
    all_apts = _get_cached_apts(conn)
    # optional 필터는 Python에서 적용 (DB 쿼리 불필요)
    filtered_apts = all_apts
    if req.min_kaptdaCnt is not None:
        filtered_apts = [a for a in filtered_apts if (a['kaptdaCnt'] or 0) >= req.min_kaptdaCnt]
    if req.build_year_min is not None:
        filtered_apts = [a for a in filtered_apts if (a['build_year'] or 0) >= req.build_year_min]

    near_keys = [
        a['apt_seq'] for a in filtered_apts
        if haversine(a['lat'], a['lng'], dest_lat, dest_lng) <= radius_km
        and (not dual or haversine(a['lat'], a['lng'], wp_2['lat'], wp_2['lng']) <= radius_km)
    ]

    if not near_keys:
        return _empty_response(wp, [], wp_2=wp_2)

    ph = ','.join('?'*len(near_keys))
    pt = ','.join('?'*len(req.pyeong_types))
    min_price_clause = ' AND deal_amount_int>=?' if req.min_price is not None else ''
    matched_params = near_keys + req.pyeong_types + [req.max_price]
    if req.min_price is not None:
        matched_params.append(req.min_price)
    matched_rows = conn.execute(
        f'SELECT DISTINCT apt_seq FROM trade_recent '
        f'WHERE apt_seq IN ({ph}) AND pyeong_type IN ({pt}) AND deal_amount_int<=?'
        f'{min_price_clause}',
        matched_params
    ).fetchall()
    matched_keys = [r['apt_seq'] for r in matched_rows]

    if not matched_keys:
        return _empty_response(wp, [], wp_2=wp_2)

    # grid_key를 인메모리 캐시에서 조회 (DB SELECT 불필요)
    matched_key_set = set(matched_keys)
    cells = sorted(set(
        a['grid_key'] for a in all_apts if a['apt_seq'] in matched_key_set
    ))

    # ─ 3. 캐시 미스 셀만 ODsay 호출 ─
    # passed_filter=0 (경로 없음)도 캐시된 결과로 간주 — 재호출 불필요
    cached_1 = set(r['origin_cell'] for r in conn.execute(
        'SELECT origin_cell FROM transit_cache WHERE wp_id=?', (wp_id,)
    ).fetchall())
    if dual:
        cached_2 = set(r['origin_cell'] for r in conn.execute(
            'SELECT origin_cell FROM transit_cache WHERE wp_id=?', (wp_id_2,)
        ).fetchall())
    else:
        cached_2 = set()

    # 셀별 직장 거리 계산 헬퍼
    def _cell_dist_to(lat, lng):
        def _fn(c):
            clat, clng = cell_center(c)
            return haversine(clat, clng, lat, lng)
        return _fn

    to_fetch_all_1 = [c for c in cells if c not in cached_1]
    to_fetch_all_2 = [c for c in cells if c not in cached_2] if dual else []

    # ── 동적 분배: wp별 미스 수를 측정 후 적은 쪽이 먼저 할당량 차지 ──
    TOTAL_LIMIT = MAX_FETCH_CELLS_PER_CALL  # 200
    half = TOTAL_LIMIT // 2                  # 100
    n1, n2 = len(to_fetch_all_1), len(to_fetch_all_2)

    if not dual:
        take_1, take_2 = min(n1, TOTAL_LIMIT), 0
    elif n1 <= half and n2 <= half:
        take_1, take_2 = n1, n2
    elif n1 <= half:
        take_1 = n1
        take_2 = min(n2, TOTAL_LIMIT - n1)
    elif n2 <= half:
        take_2 = n2
        take_1 = min(n1, TOTAL_LIMIT - n2)
    else:
        take_1, take_2 = half, half

    to_fetch_1 = sorted(to_fetch_all_1, key=_cell_dist_to(dest_lat, dest_lng))[:take_1]
    to_fetch_2 = (
        sorted(to_fetch_all_2, key=_cell_dist_to(wp_2['lat'], wp_2['lng']))[:take_2]
        if dual else []
    )
    # ODsay: 캐시 미스 셀을 백그라운드에서 처리 (응답 블로킹 없음)
    # 캐시된 transit_routes만 이번 응답에 포함하고, 미스 셀은 bg 완료 후 재검색 시 반영.
    if to_fetch_1 or to_fetch_2:
        if cfg.IS_SERVERLESS:
            background_tasks.add_task(
                _fetch_transit_bg, wp, to_fetch_1,
                wp_2 if dual else None, to_fetch_2 if dual else []
            )
        else:
            task = asyncio.create_task(
                _fetch_transit_bg(wp, to_fetch_1, wp_2 if dual else None, to_fetch_2 if dual else [])
            )
            _bg_tasks.add(task)
            task.add_done_callback(_bg_tasks.discard)

    deferred_cells_1 = n1  # 모든 미스 셀은 bg에서 처리 → 이번 응답엔 캐시 결과만
    deferred_cells_2 = n2 if dual else 0
    odsay_stats_1 = {'fetched': 0, 'passed': 0, 'failed': 0, 'elapsed_ms': 0}
    odsay_stats_2 = None
    odsay_stats = odsay_stats_1
    deferred_cells = deferred_cells_1 + deferred_cells_2

    # ─ 4. 카드 쿼리 ─
    min_cnt_clause        = ' AND a.kaptdaCnt >= ?' if req.min_kaptdaCnt is not None else ''
    build_year_clause     = ' AND a.build_year >= ?' if req.build_year_min is not None else ''
    min_price_card_clause = ' AND t.deal_amount_int >= ?' if req.min_price is not None else ''

    def _extra_params():
        p = []
        if req.min_kaptdaCnt is not None:
            p.append(req.min_kaptdaCnt)
        if req.build_year_min is not None:
            p.append(req.build_year_min)
        if req.min_price is not None:
            p.append(req.min_price)
        return p

    if not dual:
        # ── 단일 모드 (기존 쿼리 그대로) ────────────────────────
        cards_params = [wp_id, effective_max_min, req.max_price, *req.pyeong_types,
                        *_extra_params()]
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
                ROUND(AVG(t.pyeong)) AS pyeong,
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
              AND t.dealing_gbn = '중개거래'
              {min_cnt_clause}
              {build_year_clause}
              {min_price_card_clause}
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
    else:
        # ── dual 모드 — r1(wp1) + r2(wp2) self-join ────────────
        # ORDER BY: GREATEST(t1, t2) 를 portable.greatest()로 처리
        order_expr = greatest('r1.total_time_min', 'r2.total_time_min')
        cards_params = [
            wp_id, effective_max_min,
            wp_id_2, effective_max_min,
            req.max_price, *req.pyeong_types,
            *_extra_params(),
        ]
        cards = conn.execute(f"""
            SELECT
                a.apt_seq, a.apt_nm, a.umd_nm, a.kaptdaCnt, a.lat, a.lng,
                a.kaptCode,
                r1.total_time_min AS total_time_min_1,
                r1.bus_cnt AS bus_cnt_1, r1.subway_cnt AS subway_cnt_1,
                r1.step1_type, r1.step1_time_min, r1.step1_노선,
                r1.step2_type, r1.step2_time_min, r1.step2_노선,
                r1.step3_type, r1.step3_time_min, r1.step3_노선,
                r1.step4_type, r1.step4_time_min, r1.step4_노선,
                r1.step5_type, r1.step5_time_min, r1.step5_노선,
                r2.total_time_min AS total_time_min_2,
                r2.bus_cnt AS bus_cnt_2, r2.subway_cnt AS subway_cnt_2,
                r2.step1_type AS step1_type_2, r2.step1_time_min AS step1_time_min_2,
                r2.step1_노선 AS step1_노선_2,
                r2.step2_type AS step2_type_2, r2.step2_time_min AS step2_time_min_2,
                r2.step2_노선 AS step2_노선_2,
                r2.step3_type AS step3_type_2, r2.step3_time_min AS step3_time_min_2,
                r2.step3_노선 AS step3_노선_2,
                r2.step4_type AS step4_type_2, r2.step4_time_min AS step4_time_min_2,
                r2.step4_노선 AS step4_노선_2,
                r2.step5_type AS step5_type_2, r2.step5_time_min AS step5_time_min_2,
                r2.step5_노선 AS step5_노선_2,
                t.pyeong_type,
                MIN(t.deal_amount_int) AS price_low,
                MAX(t.deal_amount_int) AS price_high,
                COUNT(t.id) AS deal_count,
                AVG(t.deal_amount_int * 1.0 / NULLIF(t.pyeong, 0)) AS pyeong_price_avg,
                ROUND(AVG(t.pyeong)) AS pyeong,
                MAX(k.kaptTopFloor) AS top_floor,
                MAX(k.kaptUsedate) AS use_date
            FROM apartments a
            LEFT JOIN kapt_complexes k ON a.kaptCode = k.kaptCode
            JOIN transit_routes r1 ON a.grid_key = r1.origin_cell
            JOIN transit_routes r2 ON a.grid_key = r2.origin_cell
            JOIN trade_recent t    ON a.apt_seq  = t.apt_seq
            WHERE a.is_apt=1
              AND r1.wp_id=? AND r1.rank=1 AND r1.total_time_min<=?
              AND r2.wp_id=? AND r2.rank=1 AND r2.total_time_min<=?
              AND t.deal_amount_int<=?
              AND t.pyeong_type IN ({pt})
              AND t.dealing_gbn = '중개거래'
              {min_cnt_clause}
              {build_year_clause}
              {min_price_card_clause}
            GROUP BY
                a.apt_seq, a.apt_nm, a.umd_nm, a.kaptdaCnt, a.lat, a.lng,
                a.kaptCode,
                r1.total_time_min, r1.bus_cnt, r1.subway_cnt,
                r1.step1_type, r1.step1_time_min, r1.step1_노선,
                r1.step2_type, r1.step2_time_min, r1.step2_노선,
                r1.step3_type, r1.step3_time_min, r1.step3_노선,
                r1.step4_type, r1.step4_time_min, r1.step4_노선,
                r1.step5_type, r1.step5_time_min, r1.step5_노선,
                r2.total_time_min, r2.bus_cnt, r2.subway_cnt,
                r2.step1_type, r2.step1_time_min, r2.step1_노선,
                r2.step2_type, r2.step2_time_min, r2.step2_노선,
                r2.step3_type, r2.step3_time_min, r2.step3_노선,
                r2.step4_type, r2.step4_time_min, r2.step4_노선,
                r2.step5_type, r2.step5_time_min, r2.step5_노선,
                t.pyeong_type
            ORDER BY {order_expr}, price_low
        """, cards_params).fetchall()

    # ─ 4b–4e. 카드 extras 병렬 조회 (recent / tags / chg / comments) ─
    if cards:
        import datetime as _dt
        _now = _dt.date.today()

        def _ym(months_back: int) -> int:
            y, m = _now.year, _now.month - months_back
            while m <= 0:
                m += 12; y -= 1
            return y * 100 + m

        seqs = list({c['apt_seq'] for c in cards})
        threshold_ym = year_month_minus(3)
        ym_3mo, ym_9mo = _ym(3), _ym(9)

        recent_rows, tag_rows_raw, chg_rows_raw, comment_rows = await _fetch_card_extras(
            seqs, wp_id, threshold_ym, ym_3mo, ym_9mo
        )
    else:
        recent_rows, tag_rows_raw, chg_rows_raw, comment_rows = [], [], [], []

    if cards:
        recent_map: dict = {}
        for row in recent_rows:
            key = (row['apt_seq'], row['pyeong_type'])
            recent_map.setdefault(key, []).append({
                'pyeong': row['pyeong'],
                'floor': row['floor'],
                'amount': row['deal_amount_int'],
                'date': (
                    f"{row['deal_year'] % 100:02d}"
                    f".{row['deal_month']:02d}.{row['deal_day']:02d}"
                ),
                'gbn': row['dealing_gbn'],
            })
    else:
        recent_map = {}

    # ─ 4b-2. 3개월 평균가 맵 (배지 대표 가격용) ─
    avg_price_map: dict = {
        key: round(sum(t['amount'] for t in trades) / len(trades))
        for key, trades in recent_map.items() if trades
    }

    # ─ 4c. why_tags ─
    tag_map: dict = {}
    if cards:
        for row in tag_rows_raw:
            key = (row['apt_seq'], row['pyeong_type'])
            tag_map.setdefault(key, []).append({
                'type':   row['tag_type'],
                'label':  row['label'],
                'detail': row['detail'],
            })

    # ─ 4d. 가격 변동률 ─
    price_chg_map: dict = {}
    if cards:
        for row in chg_rows_raw:
            r_avg, p_avg = row['recent_avg'], row['past_avg']
            if r_avg and p_avg and p_avg > 0:
                pct = round((r_avg - p_avg) / p_avg * 100, 1)
                if abs(pct) >= 3.0:
                    price_chg_map[(row['apt_seq'], row['pyeong_type'])] = pct

    # ─ 4e. POI 최단거리 집계 (정렬용) ─
    poi_min_map: dict = {}
    kaptcodes = list({c['kaptCode'] for c in cards if c['kaptCode']})
    if kaptcodes:
        ph_poi = ','.join(['?'] * len(kaptcodes))
        try:
            poi_min_rows = conn.execute(f"""
                SELECT kaptCode,
                       MIN(CASE WHEN poi_lclas_cd='I' THEN walking_min END) AS nearest_park_min,
                       MIN(CASE WHEN poi_lclas_cd='D' AND poi_mlsfc_cd='D01' THEN walking_min END) AS nearest_subway_min,
                       MIN(CASE WHEN poi_lclas_cd='A' AND poi_nm LIKE '%초등%' THEN walking_min END) AS nearest_elementary_min,
                       MIN(CASE WHEN poi_lclas_cd='A' AND poi_nm NOT LIKE '%초등%' THEN walking_min END) AS nearest_mid_high_min,
                       MIN(CASE WHEN poi_lclas_cd='E' THEN walking_min END) AS nearest_mart_min
                FROM apt_walking_poi
                WHERE kaptCode IN ({ph_poi})
                GROUP BY kaptCode
            """, kaptcodes).fetchall()
            poi_min_map = {r['kaptCode']: {
                'nearest_park_min': r['nearest_park_min'],
                'nearest_subway_min': r['nearest_subway_min'],
                'nearest_elementary_min': r['nearest_elementary_min'],
                'nearest_mid_high_min': r['nearest_mid_high_min'],
                'nearest_mart_min': r['nearest_mart_min'],
            } for r in poi_min_rows}
        except Exception:
            # apt_walking_poi 미존재/조회 실패 → poi_min_map 빈 채로 진행 (POI 정렬만 비활성).
            # ⚠️ Postgres(pgBouncer)는 실패 후 트랜잭션 aborted → rollback 없이 다음 쿼리 시 500 연쇄.
            poi_min_map = {}
            try:
                conn.rollback()
            except Exception:
                pass

    # ─ 5. 카드 변환 + 추천 로직 (통근버킷 × 평형 매트릭스) ─
    raw_cards = [_card_to_dict(c, recent_map, tag_map, price_chg_map, avg_price_map, poi_min_map, dual=dual) for c in cards]
    # 대표가(3개월 평균)가 검색 범위를 벗어난 카드 제거
    # avg_price_map이 없는 카드(거래 없음)는 유지
    def _price_in_range(card: dict) -> bool:
        p = card.get('price_low')
        if not p:
            return True
        # avg_price_map에서 온 값만 필터 (recent_map 기반으로 계산된 경우)
        key = (card['apt_seq'], card['pyeong_type'])
        if key not in avg_price_map:
            return True  # fallback 값이면 필터 안 함
        if req.max_price and p > req.max_price:
            return False
        if req.min_price and p < req.min_price:
            return False
        return True
    raw_cards = [c for c in raw_cards if _price_in_range(c)]
    rec = build_recommendations(raw_cards, effective_max_min)
    buckets = rec['buckets']
    all_cards = rec['cards']

    # ─ 6. 통계 계산 ─
    stats = build_stats(all_cards, buckets)

    # ─ 7. 친구 한 마디 — 캐시된 것만 즉시 표시, 생성은 /api/comments/generate가 담당 ─
    cached_comments: dict[str, str] = {}  # card_key → comment
    if all_cards:
        for row in comment_rows:
            cached_comments[f"{row['apt_seq']}:{row['pyeong_type']}"] = row['comment']

    miss_cards = [c for c in all_cards if card_key(c) not in cached_comments]
    llm_pending = len(miss_cards) > 0

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
        'workplace_2': {
            'wp_id': wp_2['wp_id'],
            'address_input': wp_2['address_input'],
            'address_norm':  wp_2['address_norm'],
            'lat': wp_2['lat'], 'lng': wp_2['lng'],
        } if dual else None,
        'stats': stats,
        'buckets': buckets,
        'cards': all_cards,
        'meta': {
            'dual_workplace':   dual,
            'odsay_calls_made': odsay_stats['fetched'],
            'odsay_passed':     odsay_stats['passed'],
            'odsay_failed':     odsay_stats['failed'],
            'odsay_calls_made_1': odsay_stats_1['fetched'],
            'odsay_calls_made_2': odsay_stats_2['fetched'] if odsay_stats_2 else 0,
            'cache_hits':         len(cached_1) + len(cached_2),
            'odsay_elapsed_ms':   odsay_stats['elapsed_ms'],
            'llm_cached':       len(cached_comments),
            'llm_pending':      len(miss_cards),
            'llm_pending_recommend': sum(1 for c in miss_cards if c.get('is_recommended')),
            'llm_pending_regular':   sum(1 for c in miss_cards if not c.get('is_recommended')),
            'partial':          deferred_cells > 0,
            'transit_pending':  deferred_cells > 0,
            'deferred_cells':   deferred_cells,
            'deferred_cells_1': deferred_cells_1,
            'deferred_cells_2': deferred_cells_2,
            'total_cells':      len(cells),
        },
    }


def _start_comment_generation(background_tasks: BackgroundTasks, miss_cards: list, all_cards: list, wp_id: int, wp_label: str):
    if cfg.IS_SERVERLESS:
        background_tasks.add_task(_generate_comments_bg, miss_cards, all_cards, wp_id, wp_label)
        return 'background_tasks'

    task = asyncio.create_task(_generate_comments_bg(miss_cards, all_cards, wp_id, wp_label))
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    return 'asyncio_task'


# ── 백그라운드: LLM 코멘트 생성 + DB 캐싱 ───────────────────
async def _generate_comments_bg(miss_cards: list, all_cards: list, wp_id: int, wp_label: str):
    """BackgroundTask — 응답 후 실행. 별도 DB 커넥션 사용.

    miss_cards: 코멘트 생성 대상 (추천 카드 중 캐시 미스)
    all_cards : 전체 카드 (평형별 평균가 등 컨텍스트 계산용)
    """
    import time
    import traceback
    t0 = time.time()

    # Vercel 타임아웃 방지: 추천 우선으로 상한만큼만 처리, 나머지는 다음 검색 때 캐시
    rec_cards = [c for c in miss_cards if c.get('is_recommended')]
    reg_cards = [c for c in miss_cards if not c.get('is_recommended')]
    rec_cards = rec_cards[:cfg.BG_COMMENTS_MAX_REC]
    reg_cards = reg_cards[:cfg.BG_COMMENTS_MAX_REG]
    miss_cards = rec_cards + reg_cards

    rec_n = len(rec_cards)
    reg_n = len(reg_cards)
    print(f'[bg_comments] 시작 — 추천 {rec_n}개, 일반 {reg_n}개 (상한 {cfg.BG_COMMENTS_MAX_REC}/{cfg.BG_COMMENTS_MAX_REG})')
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
                entry = new_comments.get(ck, {})
                comment = entry.get('comment', '')
                # '(생성 실패)' 같은 에러 메시지는 캐시하지 않음 → 다음 검색 때 재시도
                if comment and not comment.startswith('('):
                    kind = entry.get('kind', 'regular')
                    model = cfg.SONNET_MODEL if kind == 'recommend' else cfg.HAIKU_MODEL
                    rows.append((c['apt_seq'], c['pyeong_type'], wp_id, comment, model))
            if rows:
                conn.executemany(
                    upsert_sql(
                        'apt_pt_friend_comment',
                        ['apt_seq', 'pyeong_type', 'wp_id', 'comment', 'model'],
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


# ── 백그라운드: ODsay 통근 경로 계산 (응답 블로킹 없음) ─────────
async def _fetch_transit_bg(wp, cells_1: list, wp_2=None, cells_2: list = []):
    """BackgroundTask — 미스 셀의 ODsay 경로를 계산하고 DB에 저장.
    응답 후 실행되므로 별도 DB 커넥션을 생성해 사용."""
    from app.db import connect
    conn = connect()
    try:
        if cells_1:
            await fetch_cells(conn, wp, cells_1)
        if wp_2 and cells_2:
            await fetch_cells(conn, wp_2, cells_2)
        n = len(cells_1) + len(cells_2 or [])
        print(f'[bg_transit] 완료 — wp={wp["wp_id"]}, 셀={n}개')
    except Exception as e:
        print(f'[bg_transit] 실패: {type(e).__name__}: {e}')
    finally:
        conn.close()


@router.post("/comments/generate")
async def generate_comments(req: CommentGenerateRequest, background_tasks: BackgroundTasks, conn=Depends(get_db)):
    """검색 결과 렌더 후 프론트가 호출하는 LLM 코멘트 생성 트리거."""
    cards = [c for c in req.cards if c.get('apt_seq') and c.get('pyeong_type')]
    if not cards:
        return {'started': 0, 'cached': 0, 'mode': 'none'}

    pairs = [(str(c['apt_seq']), str(c['pyeong_type'])) for c in cards]
    conds = ' OR '.join(['(apt_seq=? AND pyeong_type=?)'] * len(pairs))
    params: list = [req.wp_id]
    for seq, pt in pairs:
        params.extend([seq, pt])
    rows = conn.execute(
        f'SELECT apt_seq, pyeong_type FROM apt_pt_friend_comment '
        f"WHERE wp_id=? AND ({conds}) AND comment != ''",
        params,
    ).fetchall()
    cached = {f"{r['apt_seq']}:{r['pyeong_type']}" for r in rows}
    miss_cards = [c for c in cards if card_key(c) not in cached]
    if not miss_cards:
        return {'started': 0, 'cached': len(cached), 'mode': 'none'}

    wp_label = req.wp_label or ''
    mode = _start_comment_generation(background_tasks, miss_cards, cards, req.wp_id, wp_label)
    return {'started': len(miss_cards), 'cached': len(cached), 'mode': mode}


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
    params: list = [wp_id]
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


def _empty_response(wp, _cards, wp_2=None):
    dual = wp_2 is not None
    return {
        'wp_id': wp['wp_id'],
        'llm_pending': False,
        'workplace': {
            'address_input': wp['address_input'],
            'address_norm':  wp['address_norm'],
            'lat': wp['lat'], 'lng': wp['lng'],
        },
        'workplace_2': {
            'wp_id': wp_2['wp_id'],
            'address_input': wp_2['address_input'],
            'address_norm':  wp_2['address_norm'],
            'lat': wp_2['lat'], 'lng': wp_2['lng'],
        } if dual else None,
        'stats': {'total': 0},
        'buckets': [],
        'cards': [],
        'meta': {'dual_workplace': dual},
    }
