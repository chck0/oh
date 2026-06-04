"""
카드 직렬화 공용 헬퍼 (search.py에서 분리)

_card_to_dict          : DB row → 카드 dict (단일/맞벌이 dual 모드)
_build_transit_summary : steps 리스트 → 대중교통 요약 문자열

순수 함수 (re만 의존). search/detail/chat 어느 모듈도 import하지 않음 → 순환 없음.
search.py가 from app.cards import _card_to_dict 로 사용.
"""
import re


# ── 통근 경제성 계산 (spec-28) ───────────────────────────────
def _commute_economics(total_time_min: "int | None") -> dict:
    """수도권 교통카드 기준 월 교통비·연간 통근 시간 근사값."""
    if not total_time_min:
        return {'monthly_transit_cost': None, 'annual_commute_hours': None}
    if total_time_min <= 25:
        fare = 1500
    elif total_time_min <= 40:
        fare = 1800
    elif total_time_min <= 55:
        fare = 2100
    else:
        fare = 2300
    return {
        'monthly_transit_cost': fare * 2 * 20,
        'annual_commute_hours': round(total_time_min * 2 * 20 * 12 / 60),
    }


def _build_transit_summary(steps: list[dict], bc: int, sc: int, total_time_min: int) -> str:
    """steps 리스트 → 대중교통 요약 문자열 (wp1/wp2 공통 헬퍼)."""
    walk_min = None
    subway_line = None
    for s in steps:
        if s['type'] in ('도보', '환승도보', 'WALK') and walk_min is None:
            walk_min = s['time']
        if s['type'] in ('지하철', 'SUBWAY') and subway_line is None:
            line_raw = s['line'] or ''
            m = re.search(r'\d+호선', line_raw)
            subway_line = m.group(0) if m else (line_raw.strip() or None)

    if subway_line:
        xfer = max(sc - 1, 0)
        summary = f'{subway_line} 직통' if xfer == 0 else f'{subway_line} {xfer}회환승'
        if walk_min:
            summary += f' (도보 {walk_min}분)'
    elif bc:
        xfer = max(bc - 1, 0)
        summary = '버스 직통' if xfer == 0 else f'버스 {xfer}회환승'
        if walk_min:
            summary += f' (도보 {walk_min}분)'
    else:
        summary = f'{total_time_min}분'
    return summary


def _card_to_dict(r, recent_map: dict | None = None, tag_map: dict | None = None, price_chg_map: dict | None = None, avg_price_map: dict | None = None, dual: bool = False):
    # ── wp1 transit 파싱 ─────────────────────────────────────────
    if dual:
        bc_1, sc_1 = r['bus_cnt_1'], r['subway_cnt_1']
        steps_1 = []
        for i in range(1, 6):
            st = r[f'step{i}_type']
            if not st:
                break
            steps_1.append({'type': st, 'time': r[f'step{i}_time_min'], 'line': r[f'step{i}_노선']})
        transit_summary_1 = _build_transit_summary(steps_1, bc_1, sc_1, r['total_time_min_1'])

        # ── wp2 transit 파싱 ────────────────────────────────────
        bc_2, sc_2 = r['bus_cnt_2'], r['subway_cnt_2']
        steps_2 = []
        for i in range(1, 6):
            st = r[f'step{i}_type_2']
            if not st:
                break
            steps_2.append({'type': st, 'time': r[f'step{i}_time_min_2'], 'line': r[f'step{i}_노선_2']})
        transit_summary_2 = _build_transit_summary(steps_2, bc_2, sc_2, r['total_time_min_2'])

        total_time_min = max(r['total_time_min_1'], r['total_time_min_2'])
        # 단일 모드 호환 필드 (transit_summary = wp1 요약)
        bc, sc = bc_1, sc_1
        transit_summary = transit_summary_1
    else:
        bc, sc = r['bus_cnt'], r['subway_cnt']
        steps = []
        for i in range(1, 6):
            st = r[f'step{i}_type']
            if not st:
                break
            steps.append({'type': st, 'time': r[f'step{i}_time_min'], 'line': r[f'step{i}_노선']})
        transit_summary = _build_transit_summary(steps, bc, sc, r['total_time_min'])
        total_time_min = r['total_time_min']
        bc_1 = bc; sc_1 = sc
        transit_summary_1 = transit_summary
        bc_2 = None; sc_2 = None
        transit_summary_2 = None

    # 준공연도: kaptUsedate = "20040517" → 2004
    use_date = r['use_date'] or ''
    build_year = int(use_date[:4]) if len(use_date) >= 4 and use_date[:4].isdigit() else None

    apt_seq = r['apt_seq']
    pyeong_type = r['pyeong_type'] if 'pyeong_type' in r.keys() else None
    try:
        pa = r['pyeong_price_avg']
        pyeong_price = int(pa) if pa else None
    except (IndexError, KeyError):
        pyeong_price = None

    card = {
        'apt_seq': apt_seq, 'apt_nm': r['apt_nm'], 'umd_nm': r['umd_nm'],
        'pyeong_type': pyeong_type,
        'kaptdaCnt': int(r['kaptdaCnt'] or 0),
        'top_floor': r['top_floor'],
        'build_year': build_year,
        'lat': r['lat'], 'lng': r['lng'],
        'total_time_min': total_time_min,
        'total_time_min_1': r['total_time_min_1'] if dual else total_time_min,
        'total_time_min_2': r['total_time_min_2'] if dual else None,
        'bus_cnt': bc, 'subway_cnt': sc,
        'bus_cnt_1': bc_1, 'subway_cnt_1': sc_1,
        'bus_cnt_2': bc_2, 'subway_cnt_2': sc_2,
        'transit_summary': transit_summary,
        'transit_summary_1': transit_summary_1,
        'transit_summary_2': transit_summary_2,
        # 대표가: 3개월 평균 → 최신 거래 → MIN(fallback)
        'price_low': (avg_price_map or {}).get((apt_seq, pyeong_type))
                     or ((recent_map or {}).get((apt_seq, pyeong_type)) or [{}])[0].get('amount')
                     or r['price_low'],
        'price_high': r['price_high'],
        'pyeong_price_avg': pyeong_price,
        'deal_count': r['deal_count'],
        'recent_trades': (recent_map or {}).get((apt_seq, pyeong_type), []),
        'why_tags': (tag_map or {}).get((apt_seq, pyeong_type), []),
        'price_chg_6m_pct': (price_chg_map or {}).get((apt_seq, pyeong_type)),
        **_commute_economics(total_time_min),
    }
    return card
