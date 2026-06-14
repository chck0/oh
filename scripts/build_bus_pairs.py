"""
transit_routes 버스 step에서 고유 무방향 정류장 쌍 추출 → bus_pair_geom(status=pending) 적재 (Spec 32)

버스 step linestring = ODsay 정류장 좌표("lng,lat lng,lat ...").
인접 정류장 쌍을 무방향(a<b 정렬) 정규화해 dedup 후 적재. 라우팅 전 1회 실행.

사용법: python scripts/build_bus_pairs.py
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from app.db import connect


def main() -> None:
    conn = connect()
    pairs: set[tuple[str, str]] = set()
    rows = conn.execute(
        'SELECT ' + ', '.join(
            f'step{n}_노선, step{n}_linestring' for n in range(1, 6)
        ) + ' FROM transit_routes'
    ).fetchall()
    for r in rows:
        for k in range(5):
            line, ls = r[k * 2], r[k * 2 + 1]
            if not line or '호선' in str(line) or not ls:
                continue
            pts = ls.split()
            for a, b in zip(pts, pts[1:]):
                if a == b:
                    continue
                lo, hi = (a, b) if a < b else (b, a)
                pairs.add((lo, hi))

    conn.executemany(
        'INSERT OR IGNORE INTO bus_pair_geom (a, b, linestring, status) '
        "VALUES (?, ?, NULL, 'pending')",
        list(pairs),
    )
    conn.commit()
    n = conn.execute('SELECT COUNT(*) FROM bus_pair_geom').fetchone()[0]
    pend = conn.execute(
        "SELECT COUNT(*) FROM bus_pair_geom WHERE status='pending'"
    ).fetchone()[0]
    conn.close()
    print(f'고유 무방향 쌍 적재: {len(pairs)} | bus_pair_geom 총 {n} | pending {pend}')


if __name__ == '__main__':
    main()
