"""
버스 step을 bus_seq_geom(시퀀스 라우팅) 도로곡선으로 교체 (Spec 32 개선, backfill)

raw JSON과 transit_routes를 시그니처(총시간+step type·노선) 매칭해 정렬,
각 버스 step의 원본 정류장 시퀀스 → bus_seq_geom 조회로 도로곡선 교체.
지하철·도보 step은 그대로(현재 transit_routes 값 유지).

사용법: (route_bus_seq.py 완료 후) python scripts/backfill_bus_seq.py
"""
from __future__ import annotations
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from app.db import connect
from app.transit import to_steps, step_cols, MAX_STEPS

RAW = Path('data/raw/odsay/workplaces')


def _row_sig(row):
    steps = tuple((row[2 + k * 2] or '', row[3 + k * 2] or '')
                  for k in range(MAX_STEPS))
    return (row[1], steps)


def main() -> None:
    conn = connect()
    seqmap = {s: ls for s, ls, st in conn.execute(
        "SELECT stops, linestring, status FROM bus_seq_geom") if ls}
    print(f'bus_seq_geom: {len(seqmap)}')

    set_cols = ', '.join(f'step{n}_linestring=?' for n in range(1, MAX_STEPS + 1))
    upd = (f'UPDATE transit_routes SET {set_cols} '
           'WHERE origin_cell=? AND wp_id=? AND rank=?')
    selcols = ', '.join(f'step{n}_type, step{n}_노선' for n in range(1, MAX_STEPS + 1))
    selsql = (f'SELECT rank, total_time_min, {selcols} '
              'FROM transit_routes WHERE origin_cell=? AND wp_id=? ORDER BY rank')

    changed = 0
    t0 = time.time()
    for wp in sorted(RAW.glob('wp_*')):
        m = re.match(r'wp_(\d+)_', wp.name)
        if not m or not (wp / 'cells').exists():
            continue
        wp_id = int(m.group(1))
        for cf in (wp / 'cells').glob('*.json'):
            oc = cf.stem
            try:
                data = json.loads(cf.read_text(encoding='utf-8'))
            except Exception:
                continue
            paths = data.get('result', {}).get('path', [])
            if not paths:
                continue
            sigmap = defaultdict(list)
            for p in paths:
                steps = to_steps(p.get('subPath', []))
                sig_steps, busls = [], {}
                for i in range(1, MAX_STEPS + 1):
                    c = step_cols(steps, i)
                    sig_steps.append((c[0] or '', c[3] or ''))
                    if c[0] == '버스' and c[6]:
                        busls[i] = c[6]
                sig = (p.get('info', {}).get('totalTime'), tuple(sig_steps))
                sigmap[sig].append(busls)
            for row in conn.execute(selsql, (oc, wp_id)).fetchall():
                q = sigmap.get(_row_sig(row))
                if not q:
                    continue
                busls = q.pop(0)
                if not busls:
                    continue
                # 현재 step linestring 읽어서 버스 step만 교체
                cur = conn.execute(
                    'SELECT ' + ', '.join(
                        f'step{n}_linestring' for n in range(1, MAX_STEPS + 1)) +
                    ' FROM transit_routes WHERE origin_cell=? AND wp_id=? AND rank=?',
                    (oc, wp_id, row[0])).fetchone()
                new = list(cur)
                hit = False
                for i, stops in busls.items():
                    geom = seqmap.get(stops)
                    if geom:
                        new[i - 1] = geom
                        hit = True
                if hit:
                    conn.execute(upd, (*new, oc, wp_id, row[0]))
                    changed += 1
        conn.commit()
    conn.close()
    print(f'완료: {changed}행 버스곡선 갱신 ({time.time()-t0:.0f}s)')


if __name__ == '__main__':
    main()
