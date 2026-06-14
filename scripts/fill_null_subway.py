"""
transit_routes의 NULL 지하철 step linestring을 역명 기반으로 채움 (Spec 31, 100% 목표).

raw ODsay JSON이 없는 셀(예: wp9/wp14 일부)은 backfill_pair_geom이 못 채워 NULL로 남는다.
transit_routes가 이미 가진 step 출발/도착 역명으로 GTFS 좌표를 찾아 스티칭 → NULL을 메움.
raw에 의존하지 않으므로 모든 셀에 적용 가능.

사용법:
    python scripts/backfill_pair_geom.py   # 먼저 raw 기반 backfill
    python scripts/fill_null_subway.py     # 그 뒤 NULL 보충
"""
from __future__ import annotations
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from app.db import connect
from app.transit import MAX_STEPS
from app.gtfs_subway import build_subway_by_name


def main() -> None:
    conn = connect()
    cols = ['origin_cell', 'wp_id', 'rank']
    for n in range(1, MAX_STEPS + 1):
        cols += [f'step{n}_type', f'step{n}_노선',
                 f'step{n}_출발', f'step{n}_도착', f'step{n}_linestring']
    rows = conn.execute(f'SELECT {", ".join(cols)} FROM transit_routes').fetchall()

    filled = 0
    still_null = 0
    t0 = time.time()
    for r in rows:
        oc, wp, rank = r[0], r[1], r[2]
        updates: dict[int, str] = {}
        for k in range(MAX_STEPS):
            off = 3 + k * 5
            stype, line, frm, to, ls = r[off], r[off + 1], r[off + 2], r[off + 3], r[off + 4]
            if stype != '지하철' or not line:
                continue
            # 모든 지하철 step을 GTFS 트랙으로 재도출(멱등) — 버스 backfill이
            # 비-호선 철도(신림선·경의중앙선 등)를 도로좌표로 덮은 것도 복원.
            new = build_subway_by_name(line, frm, to)
            if new and len(new.split()) >= 2:
                if new != ls:
                    updates[k + 1] = new
            elif not ls:
                still_null += 1
        if updates:
            set_clause = ', '.join(f'step{n}_linestring=?' for n in updates)
            vals = list(updates.values()) + [oc, wp, rank]
            conn.execute(
                f'UPDATE transit_routes SET {set_clause} '
                'WHERE origin_cell=? AND wp_id=? AND rank=?',
                vals,
            )
            filled += len(updates)

    conn.commit()
    conn.close()
    print(f'NULL 지하철 step 채움: {filled}개 / 여전히 NULL: {still_null}개 '
          f'({time.time() - t0:.1f}s)')


if __name__ == '__main__':
    main()
