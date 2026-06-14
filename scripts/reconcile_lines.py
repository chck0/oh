"""
GTFS 지하철 노선 ↔ OSM 계통 키 정합 → line_map 적재 + 커버리지 리포트 (Spec 31, US-002)

매칭 규칙:
  GTFS (line_norm, region) → OSM 키 중 line_norm으로 시작하는 것 전부 (1:N)
  예) '1호선'(S-1) → OSM '1호선', '1호선경부선계통', '1호선경인선계통' ...
  ※ region(수도권/부산) 구분은 build_pair_geom에서 역 좌표(bbox)로 처리되므로
    동명 노선도 같은 OSM 키 후보로 매핑하고, 곡선 생성 시 좌표로 올바른 shape를 고른다.

미매칭(OSM 키 후보 0개) GTFS 노선과, 한 번도 안 쓰인 OSM 키를 리포트로 출력.

사용법:
    python scripts/reconcile_lines.py
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from app.db import connect
from app.subway_shapes import _load_index


# GTFS line_norm → OSM 키 명시 별칭 (startswith로 안 잡히는 명칭 불일치 보정)
# 리포트의 "미매칭 GTFS 노선" + "미사용 OSM 키"를 대조해 확정.
_GTFS_OSM_ALIAS: dict[str, list[str]] = {
    'gtxa':         ['a선'],                      # GTX-A
    '공항철도':     ['인천국제공항철도일반열차'],
    '김포도시철도': ['김포골드라인'],
    '우이신설경전철': ['우이신설선'],
    '김해경전철':   ['부산김해경전철'],
}


def _candidate_keys(line_norm: str, osm_keys: list[str]) -> list[str]:
    if not line_norm:
        return []
    keyset = set(osm_keys)
    cands = [k for k in osm_keys if k.startswith(line_norm)]
    for alias in _GTFS_OSM_ALIAS.get(line_norm, []):
        if alias in keyset and alias not in cands:
            cands.append(alias)
    return cands


def main() -> None:
    osm_index = _load_index()
    osm_keys = sorted(osm_index.keys())
    if not osm_keys:
        print('OSM 인덱스 비어있음 — data/subway_shapes_kr.json 확인')
        sys.exit(1)

    conn = connect()
    try:
        # GTFS 노선의 distinct (line_norm, region)
        gtfs_lines = conn.execute(
            'SELECT DISTINCT line_norm, region FROM gtfs_subway_route '
            'ORDER BY region, line_norm'
        ).fetchall()

        map_rows = []
        unmatched = []
        used_keys: set[str] = set()

        for line_norm, region in gtfs_lines:
            cands = _candidate_keys(line_norm, osm_keys)
            if not cands:
                unmatched.append((line_norm, region))
                continue
            for k in cands:
                map_rows.append((line_norm, region, k, 1))
                used_keys.add(k)

        conn.execute('DELETE FROM line_map')
        conn.executemany(
            'INSERT OR REPLACE INTO line_map '
            '(gtfs_line_norm, gtfs_region, osm_line_key, verified) '
            'VALUES (?, ?, ?, ?)',
            map_rows,
        )
        conn.commit()

        unused_keys = [k for k in osm_keys if k not in used_keys]

        # ── 리포트 ──
        print(f'GTFS 노선(line_norm,region): {len(gtfs_lines)}개')
        print(f'line_map 매핑 행: {len(map_rows)}개 (1:N)')
        print(f'매칭된 OSM 키: {len(used_keys)}/{len(osm_keys)}')
        print()

        # 수도권(S-1) 미매칭은 심각, 그 외는 OSM 커버리지 밖일 수 있음
        s1_unmatched = [(l, r) for l, r in unmatched if r == 'S-1']
        other_unmatched = [(l, r) for l, r in unmatched if r != 'S-1']

        print(f'■ 미매칭 GTFS 노선: {len(unmatched)}개')
        if s1_unmatched:
            print(f'  [수도권 S-1, 확인 필요] {len(s1_unmatched)}개:')
            for l, r in s1_unmatched:
                print(f'    - {l} ({r})')
        else:
            print('  [수도권 S-1] 미매칭 0개 ✅')
        if other_unmatched:
            print(f'  [그 외 권역, OSM 수도권 커버리지 밖 추정] {len(other_unmatched)}개:')
            for l, r in other_unmatched:
                print(f'    - {l} ({r})')
        print()

        print(f'■ 미사용 OSM 키: {len(unused_keys)}개')
        for k in unused_keys:
            print(f'    - {k}')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
