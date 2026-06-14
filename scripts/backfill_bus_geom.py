"""
transit_routes 버스 step의 정류장 직선을 도로 곡선으로 교체 (Spec 32, Phase 4)

각 버스 step의 정류장 좌표 인접쌍을 bus_pair_geom에서 조회해 이어붙임.
멱등성: step의 인접쌍이 bus_pair_geom 키(=정류장 좌표)에 있을 때만 처리.
라우팅된 결과는 도로 좌표라 키가 아니므로 재실행해도 재처리되지 않음.

사용법: (route_bus_pairs.py 완료 후) python scripts/backfill_bus_geom.py
"""
from __future__ import annotations
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from app.db import connect
from app.transit import MAX_STEPS


def _pair_points(cache, a, b):
    """정류장쌍 a→b 도로 좌표 리스트. 없으면 None."""
    lo, hi = (a, b) if a < b else (b, a)
    ls = cache.get((lo, hi))
    if ls is None:
        return None
    pts = [(float(x), float(y)) for x, y in (p.split(',') for p in ls.split())]
    return pts if (a == lo) else pts[::-1]


def _stitch(cache, stops):
    """정류장 시퀀스 → 쌍 이어붙인 도로 곡선. 모든 쌍이 캐시에 있어야 함."""
    out = []
    for a, b in zip(stops, stops[1:]):
        if a == b:
            continue
        pts = _pair_points(cache, a, b)
        if pts is None:
            return None   # 캐시에 없는 쌍 → 이 step은 정류장 step 아님(이미 라우팅됨)
        if out and pts and out[-1] == pts[0]:
            out.extend(pts[1:])
        else:
            out.extend(pts)
    return out if len(out) >= 2 else None


def main() -> None:
    conn = connect()
    cache = {(a, b): ls for a, b, ls in conn.execute(
        "SELECT a, b, linestring FROM bus_pair_geom WHERE linestring IS NOT NULL")}
    print(f'bus_pair_geom 캐시: {len(cache)}')

    set_sql = ', '.join(f'step{n}_linestring=?' for n in range(1, MAX_STEPS + 1))
    sel = ', '.join(
        f'step{n}_노선, step{n}_linestring' for n in range(1, MAX_STEPS + 1))
    rows = conn.execute(
        f'SELECT origin_cell, wp_id, rank, {sel} FROM transit_routes').fetchall()

    updated = changed = 0
    t0 = time.time()
    for r in rows:
        oc, wp, rank = r[0], r[1], r[2]
        new_ls = []
        row_changed = False
        for k in range(MAX_STEPS):
            line = r[3 + k * 2]
            ls = r[4 + k * 2]
            if line and '호선' not in str(line) and ls:
                stops = ls.split()
                stitched = _stitch(cache, stops)
                if stitched:
                    new_ls.append(' '.join(f'{x},{y}' for x, y in stitched))
                    row_changed = True
                    continue
            new_ls.append(ls)
        if row_changed:
            conn.execute(
                f'UPDATE transit_routes SET {set_sql} '
                'WHERE origin_cell=? AND wp_id=? AND rank=?',
                (*new_ls, oc, wp, rank))
            changed += 1
        updated += 1
        if updated % 20000 == 0:
            conn.commit()
            print(f'  {updated}행 처리, {changed}행 갱신 ({time.time() - t0:.0f}s)')
    conn.commit()
    conn.close()
    print(f'완료: {changed}행 버스곡선 갱신 ({time.time() - t0:.0f}s)')


if __name__ == '__main__':
    main()
