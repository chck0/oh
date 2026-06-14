"""
transit_routes.step*_linestring 백필 스크립트

이미 저장된 data/raw/**/*.json 파일을 읽어서
passStopList.stations 좌표로 linestring을 재구성 후 DB에 업데이트.

사용법:
    python scripts/backfill_linestring.py          # dry-run
    python scripts/backfill_linestring.py --apply  # 실제 적용
"""
from __future__ import annotations
import argparse, json, re, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import sqlite3
from config import cfg
from app.transit import to_steps, step_cols, MAX_STEPS

RAW_ROOT = Path('data/raw/odsay/workplaces')


def _ls_from_stations(stations: list) -> str | None:
    pts = [f"{s['x']},{s['y']}" for s in stations if s.get('x') and s.get('y')]
    return ' '.join(pts) if len(pts) >= 2 else None


def _linestrings_all_ranks(raw_path: Path) -> list[list[str | None]] | None:
    """raw JSON → rank별 [ls1..ls5] 리스트. paths 순서가 rank 순서."""
    try:
        data = json.loads(raw_path.read_text(encoding='utf-8'))
    except Exception:
        return None
    if 'result' not in data:
        return None
    paths = data['result'].get('path', [])
    if not paths:
        return None
    result = []
    for path in paths:
        steps = to_steps(path.get('subPath', []))
        result.append([step_cols(steps, i)[6] for i in range(1, MAX_STEPS + 1)])
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    if not RAW_ROOT.exists():
        print(f'raw 디렉토리 없음: {RAW_ROOT}')
        return

    # wp_NNNN__ 패턴에서 wp_id 추출
    wp_dirs = list(RAW_ROOT.glob('wp_*'))
    print(f'직장 디렉토리: {len(wp_dirs)}개')

    db_url = cfg.DATABASE_URL
    if not db_url or db_url.startswith('postgresql'):
        print('SQLite 모드가 아님 — DATABASE_URL 확인')
        return
    conn = sqlite3.connect(db_url)
    updated = skipped = errors = 0
    t0 = time.time()

    for wp_dir in sorted(wp_dirs):
        m = re.match(r'wp_(\d+)_', wp_dir.name)
        if not m:
            continue
        wp_id = int(m.group(1))
        cells_dir = wp_dir / 'cells'
        if not cells_dir.exists():
            continue

        cell_files = list(cells_dir.glob('*.json'))
        for cf in cell_files:
            origin_cell = cf.stem  # R08366C28227

            all_ranks = _linestrings_all_ranks(cf)
            if all_ranks is None:
                skipped += 1
                continue

            if args.apply:
                # DB에서 해당 origin_cell+wp_id의 rank 목록 조회
                rows = conn.execute(
                    'SELECT rank FROM transit_routes WHERE origin_cell=? AND wp_id=? ORDER BY rank',
                    (origin_cell, wp_id)
                ).fetchall()
                for row in rows:
                    rank = row[0]
                    rank_idx = rank - 1
                    if rank_idx >= len(all_ranks):
                        continue
                    ls_list = all_ranks[rank_idx]
                    if not any(ls for ls in ls_list):
                        continue
                    try:
                        conn.execute("""
                            UPDATE transit_routes
                               SET step1_linestring=?,
                                   step2_linestring=?,
                                   step3_linestring=?,
                                   step4_linestring=?,
                                   step5_linestring=?
                             WHERE origin_cell=? AND wp_id=? AND rank=?
                        """, (*ls_list, origin_cell, wp_id, rank))
                        updated += 1
                    except Exception as e:
                        errors += 1
                        print(f'  ERROR {origin_cell} wp={wp_id} rank={rank}: {e}')
            else:
                # dry-run: rank별 업데이트 건수 카산
                rows = conn.execute(
                    'SELECT COUNT(*) FROM transit_routes WHERE origin_cell=? AND wp_id=?',
                    (origin_cell, wp_id)
                ).fetchone()
                updated += rows[0] if rows else 0

    if args.apply:
        conn.commit()

    elapsed = time.time() - t0
    mode = 'APPLY' if args.apply else 'DRY-RUN'
    print(f'[{mode}] 업데이트={updated:,}  스킵={skipped:,}  오류={errors}  ({elapsed:.1f}s)')
    conn.close()


if __name__ == '__main__':
    main()
