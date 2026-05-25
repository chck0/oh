"""
trade_recent + kapt_complexes → trade_tags 사전 계산

추천 카드 "저가 근거(Why this price)" 태그를 공공데이터 기반으로 자동 생성.

태그 종류:
    floor     — 최저가 거래의 층수 특이점 (1층 / 저층 / 고층)
    price_chg — 직전 거래 대비 ±5% 이상 가격 변동 (6개월 이내 기준)

실행:
    python scripts/tag_price_reason.py
    python scripts/tag_price_reason.py --apt-seq APT001  # 단일 단지만
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')

from app.db import connect as db_connect
from app.portable import upsert_sql, USE_PG


# ── 순수 함수 (테스트 대상) ────────────────────────────────────

def calc_floor_tag(floor: int | None, top_floor: int | None) -> dict | None:
    """층수 기반 태그 계산.

    Args:
        floor:     해당 거래의 층수
        top_floor: 단지 최고층 (kapt_complexes.kaptTopFloor)

    Returns:
        태그 dict {'type', 'label', 'detail'} 또는 None
    """
    if not floor or floor <= 0:
        return None

    # 1층 정확히 → 무조건 1층 태그 (비율보다 우선)
    if floor == 1:
        return {'type': 'floor', 'label': '1층 매물', 'detail': None}

    if not top_floor or top_floor <= 0:
        return None

    ratio = floor / top_floor

    if ratio <= 0.15:
        return {
            'type': 'floor',
            'label': '저층 매물',
            'detail': f'전체 {top_floor}층 중 {floor}층',
        }
    if ratio <= 0.30:
        return {
            'type': 'floor',
            'label': '1층대 매물',
            'detail': f'전체 {top_floor}층 중 {floor}층',
        }
    if ratio >= 0.85:
        return {
            'type': 'floor',
            'label': '고층 매물',
            'detail': f'전체 {top_floor}층 중 {floor}층',
        }
    return None


def calc_price_chg_tag(
    curr_amount: int | None,
    prev_amount: int | None,
    months_gap: int | None,
) -> dict | None:
    """직전 거래 대비 가격 변동 태그 계산.

    Args:
        curr_amount: 현재(최신) 거래가 (만원)
        prev_amount: 직전 거래가 (만원)
        months_gap:  두 거래 사이 개월 수

    Returns:
        태그 dict 또는 None
    """
    if not curr_amount or not prev_amount or prev_amount <= 0:
        return None
    if months_gap is None or months_gap > 6:
        return None

    pct = round((curr_amount - prev_amount) / prev_amount * 100)

    if pct <= -5:
        return {
            'type': 'price_chg',
            'label': f'직전比 {pct}%',
            'detail': f'6개월 내 직전 거래 대비 {pct}%',
        }
    if pct >= 5:
        return {
            'type': 'price_chg',
            'label': f'최근 +{pct}% 상승',
            'detail': f'6개월 내 직전 거래 대비 +{pct}%',
        }
    return None


def _months_between(y1: int, m1: int, y2: int, m2: int) -> int:
    """두 연월 사이 개월 수 (양수 = y2m2가 더 최근)."""
    return (y2 - y1) * 12 + (m2 - m1)


# ── DB 조회 + 태그 계산 + 저장 ────────────────────────────────

def _fetch_min_price_rows(conn) -> list:
    """평형별 최저가 거래의 층수 + 단지 최고층 반환.

    ROW_NUMBER() 으로 (apt_seq, pyeong_type) 별 deal_amount_int 최소 행만 추출.
    SQLite 3.25+ / Postgres 양쪽 호환.
    """
    return conn.execute("""
        WITH ranked AS (
            SELECT t.apt_seq,
                   t.pyeong_type,
                   t.floor,
                   t.deal_amount_int,
                   k.kaptTopFloor,
                   ROW_NUMBER() OVER (
                       PARTITION BY t.apt_seq, t.pyeong_type
                       ORDER BY t.deal_amount_int ASC,
                                t.deal_year DESC,
                                t.deal_month DESC,
                                t.deal_day DESC
                   ) AS rn
            FROM trade_recent t
            JOIN apartments a ON t.apt_seq = a.apt_seq
            LEFT JOIN kapt_complexes k ON a.kaptCode = k.kaptCode
        )
        SELECT apt_seq, pyeong_type, floor, deal_amount_int, kaptTopFloor
        FROM ranked
        WHERE rn = 1
    """).fetchall()


def _fetch_recent_two_rows(conn) -> list:
    """평형별 최근 2개 거래 (가격 변동 계산용)."""
    return conn.execute("""
        WITH ranked AS (
            SELECT apt_seq, pyeong_type, deal_amount_int, deal_year, deal_month,
                   ROW_NUMBER() OVER (
                       PARTITION BY apt_seq, pyeong_type
                       ORDER BY deal_year DESC, deal_month DESC, deal_day DESC
                   ) AS rn
            FROM trade_recent
        )
        SELECT apt_seq, pyeong_type, deal_amount_int, deal_year, deal_month, rn
        FROM ranked
        WHERE rn <= 2
        ORDER BY apt_seq, pyeong_type, rn
    """).fetchall()


def run(conn, apt_seq_filter: str | None = None) -> int:
    """trade_tags 전체 재계산 후 저장.

    Args:
        conn:             DB 연결 (sqlite3 또는 psycopg)
        apt_seq_filter:   특정 단지만 처리 (None = 전체)

    Returns:
        저장된 태그 행 수
    """
    now = datetime.utcnow().isoformat()
    tags: list[tuple] = []

    # ── 1. floor 태그 ──────────────────────────────────────────
    for row in _fetch_min_price_rows(conn):
        apt = row[0] if isinstance(row, (tuple, list)) else row['apt_seq']
        pt = row[1] if isinstance(row, (tuple, list)) else row['pyeong_type']
        fl = row[2] if isinstance(row, (tuple, list)) else row['floor']
        top = row[4] if isinstance(row, (tuple, list)) else row['kaptTopFloor']

        if apt_seq_filter and apt != apt_seq_filter:
            continue

        tag = calc_floor_tag(fl, top)
        if tag:
            tags.append((apt, pt, tag['type'], tag['label'], tag['detail'], now))

    # ── 2. price_chg 태그 ──────────────────────────────────────
    # 평형별로 rn=1(최신), rn=2(직전) 쌍을 묶어 처리
    pairs: dict[tuple, dict] = {}
    for row in _fetch_recent_two_rows(conn):
        apt = row[0] if isinstance(row, (tuple, list)) else row['apt_seq']
        pt = row[1] if isinstance(row, (tuple, list)) else row['pyeong_type']
        amt = row[2] if isinstance(row, (tuple, list)) else row['deal_amount_int']
        yr = row[3] if isinstance(row, (tuple, list)) else row['deal_year']
        mo = row[4] if isinstance(row, (tuple, list)) else row['deal_month']
        rn = row[5] if isinstance(row, (tuple, list)) else row['rn']

        if apt_seq_filter and apt != apt_seq_filter:
            continue

        key = (apt, pt)
        pairs.setdefault(key, {})
        if rn == 1:
            pairs[key]['curr'] = (amt, yr, mo)
        elif rn == 2:
            pairs[key]['prev'] = (amt, yr, mo)

    for (apt, pt), d in pairs.items():
        if 'curr' not in d or 'prev' not in d:
            continue
        curr_amt, c_y, c_m = d['curr']
        prev_amt, p_y, p_m = d['prev']
        gap = _months_between(p_y, p_m, c_y, c_m)

        tag = calc_price_chg_tag(curr_amt, prev_amt, gap)
        if tag:
            tags.append((apt, pt, tag['type'], tag['label'], tag['detail'], now))

    if not tags:
        print('[tag_price_reason] 생성된 태그 없음')
        return 0

    # ── 3. trade_tags upsert ────────────────────────────────────
    sql = upsert_sql(
        'trade_tags',
        ['apt_seq', 'pyeong_type', 'tag_type', 'label', 'detail', 'calc_date'],
        pk_cols=['apt_seq', 'pyeong_type', 'tag_type'],
    )
    conn.executemany(sql, tags)
    conn.commit()
    print(f'[tag_price_reason] {len(tags)}개 태그 저장 완료')
    return len(tags)


# ── CLI 진입점 ────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description='trade_tags 사전 계산')
    parser.add_argument('--apt-seq', help='특정 단지만 처리 (예: APT001)')
    args = parser.parse_args()

    conn = db_connect()
    try:
        # trade_tags 테이블 없으면 생성
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trade_tags (
                apt_seq     TEXT,
                pyeong_type TEXT,
                tag_type    TEXT,
                label       TEXT,
                detail      TEXT,
                calc_date   TEXT,
                PRIMARY KEY (apt_seq, pyeong_type, tag_type)
            )
        """)
        conn.commit()
        run(conn, apt_seq_filter=args.apt_seq)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
