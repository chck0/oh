"""
transit_routes.step*_linestring 재backfill — 지하철 step을 GTFS순서+OSM역쌍곡선으로 교체 (Spec 31, US-004)

raw ODsay JSON을 읽되, fetch_cells가 filter/rank로 raw path를 재정렬·선별하므로
position(enumerate) 기반이 아니라 **시그니처(총시간 + step별 type·노선)로 transit_routes
행과 raw path를 매칭**해 올바른 rank에 기록한다. (position 기반은 misalignment 발생)

지하철 step은 app.gtfs_subway.build_subway_linestring으로 스티칭, 그 외(도보/버스/환승)는
ODsay 원본 linestring 유지. 멱등(raw JSON이 원천).

사용법:
    python scripts/backfill_pair_geom.py            # 전체 wp
    python scripts/backfill_pair_geom.py --wp 3 7   # 특정 wp만
"""
from __future__ import annotations
import argparse
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
from app.gtfs_subway import build_subway_linestring, enrich_odsay_pairs

RAW_ROOT = Path('data/raw/odsay/workplaces')


def _final_ls(step_type: str, line: str, odsay_ls: str | None) -> str | None:
    """지하철 step이면 GTFS+OSM 스티칭으로 치환, 실패/그외는 ODsay 원본 유지."""
    if step_type == '지하철' and odsay_ls:
        pts = odsay_ls.split()
        if len(pts) >= 2:
            try:
                blng, blat = map(float, pts[0].split(','))
                alng, alat = map(float, pts[-1].split(','))
            except ValueError:
                return odsay_ls
            stitched = build_subway_linestring(line, blng, blat, alng, alat)
            if stitched:
                return stitched
            # 2차: GTFS에 없는 노선(별내선·GTX-A 북부)은 ODsay 순서+OSM 곡선
            enriched = enrich_odsay_pairs(line, odsay_ls)
            if enriched:
                return enriched
    return odsay_ls


def _path_sig_and_ls(path: dict) -> tuple[tuple, list[str | None]]:
    """raw path → (시그니처, [ls1..ls5]). 시그니처 = (총시간, ((type,노선) x5))."""
    steps = to_steps(path.get('subPath', []))
    sig_steps = []
    ls_row = []
    for i in range(1, MAX_STEPS + 1):
        cols = step_cols(steps, i)
        step_type, line, odsay_ls = cols[0], cols[3], cols[6]
        sig_steps.append((step_type or '', line or ''))
        ls_row.append(_final_ls(step_type, line, odsay_ls))
    total = path.get('info', {}).get('totalTime')
    return (total, tuple(sig_steps)), ls_row


def _row_sig(row) -> tuple:
    """transit_routes 행 → 시그니처 (raw path와 동일 형식)."""
    sig_steps = []
    for k in range(MAX_STEPS):
        off = 2 + k * 2   # row = (rank, total, s1_type, s1_노선, s2_type, ...)
        sig_steps.append((row[off] or '', row[off + 1] or ''))
    return (row[1], tuple(sig_steps))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--wp', nargs='*', type=int, help='특정 wp_id만 (생략 시 전체)')
    args = ap.parse_args()

    if not RAW_ROOT.exists():
        print(f'raw 디렉토리 없음: {RAW_ROOT}')
        sys.exit(1)

    wp_filter = set(args.wp) if args.wp else None
    set_cols = ', '.join(f'step{n}_linestring=?' for n in range(1, MAX_STEPS + 1))
    update_sql = (
        f'UPDATE transit_routes SET {set_cols} '
        'WHERE origin_cell=? AND wp_id=? AND rank=?'
    )
    sel_cols = ', '.join(
        f'step{n}_type, step{n}_노선' for n in range(1, MAX_STEPS + 1))
    select_sql = (
        f'SELECT rank, total_time_min, {sel_cols} '
        'FROM transit_routes WHERE origin_cell=? AND wp_id=? ORDER BY rank'
    )

    conn = connect()
    updated = matched = unmatched = skipped = 0
    t0 = time.time()
    try:
        for wp_dir in sorted(RAW_ROOT.glob('wp_*')):
            m = re.match(r'wp_(\d+)_', wp_dir.name)
            if not m:
                continue
            wp_id = int(m.group(1))
            if wp_filter and wp_id not in wp_filter:
                continue
            cells_dir = wp_dir / 'cells'
            if not cells_dir.exists():
                continue

            for cf in cells_dir.glob('*.json'):
                origin_cell = cf.stem
                try:
                    data = json.loads(cf.read_text(encoding='utf-8'))
                except Exception:
                    skipped += 1
                    continue
                paths = data.get('result', {}).get('path', [])
                if not paths:
                    skipped += 1
                    continue

                # 시그니처 → ls_list 큐 (동일 시그니처 중복 대비)
                sig_map: dict[tuple, list] = defaultdict(list)
                for p in paths:
                    sig, ls_row = _path_sig_and_ls(p)
                    sig_map[sig].append(ls_row)

                rows = conn.execute(select_sql, (origin_cell, wp_id)).fetchall()
                for row in rows:
                    sig = _row_sig(row)
                    queue = sig_map.get(sig)
                    if not queue:
                        unmatched += 1
                        continue
                    ls_list = queue.pop(0)
                    conn.execute(update_sql, (*ls_list, origin_cell, wp_id, row[0]))
                    updated += 1
                    matched += 1

            print(f'  wp_{wp_id}: 누적 갱신 {updated} (미매칭 {unmatched})')

        conn.commit()
    finally:
        conn.close()

    print(f'완료: {updated}행 갱신, 미매칭 {unmatched}, 스킵 {skipped} '
          f'({time.time() - t0:.1f}s)')


if __name__ == '__main__':
    main()
