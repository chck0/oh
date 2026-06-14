"""
인접 역쌍별 OSM 곡선 사전 생성 → subway_pair_geom 적재 (Spec 31, US-003)

각 GTFS 지하철 노선의 정차 순서를 인접 역쌍으로 분해하고,
line_map이 지정한 OSM 계통 키 중 좌표(bbox)로 맞는 곡선을 골라 저장.
인접 역쌍 단위라 분기 모호성이 거의 없어 OSM 매칭이 안 꼬임.

사용법:
    python scripts/build_pair_geom.py
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from app.db import connect
from app.subway_shapes import get_segment_by_keys

# 인접 역쌍 bbox margin: 역간 거리에 비례(외곽 긴 역간 곡선 허용), 최소 ~1.5km
_MIN_MARGIN = 0.015
_SPAN_RATIO = 0.6
# 곡선 품질 검증: OSM way 불연속으로 슬라이스 내부에 점프가 생기거나
# 우회로(detour)가 끼면 bbox만으론 못 거른다 → 내부 연속성·길이비율로 추가 검증.
_MAX_DETOUR = 2.2          # 곡선 경로길이 / 직선거리 상한 (우회로 차단)
# 텔레포트(OSM way 불연속): 단일 점프가 역간 직선거리를 넘으면 비정상.
# 직선 구간의 정상적 sparse 샘플링은 허용하도록 '상대' 임계 사용.
_INNER_GAP_RATIO = 1.1
_INNER_GAP_FLOOR = 0.002   # ~0.18km 절대 하한 (아주 짧은 역간 노이즈 방지)


def _curve_ok(ls: str, slng: float, slat: float, elng: float, elat: float) -> bool:
    pts = [(float(x), float(y)) for x, y in (p.split(',') for p in ls.split())]
    if len(pts) < 2:
        return False
    straight = ((slng - elng) ** 2 + (slat - elat) ** 2) ** 0.5
    gap_limit = straight * _INNER_GAP_RATIO + _INNER_GAP_FLOOR
    plen = 0.0
    for a, b in zip(pts, pts[1:]):
        g = ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
        if g > gap_limit:           # 내부 텔레포트(way 불연속)
            return False
        plen += g
    if plen > _MAX_DETOUR * straight + 0.003:   # 우회로
        return False
    return True


def _load_line_map(conn) -> dict[tuple[str, str], list[str]]:
    m: dict[tuple[str, str], list[str]] = {}
    for line_norm, region, key in conn.execute(
        'SELECT gtfs_line_norm, gtfs_region, osm_line_key FROM line_map'
    ):
        m.setdefault((line_norm, region), []).append(key)
    return m


def _load_route_sequences(conn):
    """반환: [(line_norm, region, [(stop_id, lng, lat), ...]), ...] 노선별 순서."""
    routes = conn.execute(
        'SELECT route_id, line_norm, region FROM gtfs_subway_route'
    ).fetchall()
    result = []
    for route_id, line_norm, region in routes:
        seq = conn.execute(
            '''SELECT s.stop_id, st.lng, st.lat
               FROM gtfs_subway_seq s
               JOIN gtfs_subway_station st ON st.stop_id = s.stop_id
               WHERE s.route_id = ?
               ORDER BY s.seq''',
            (route_id,),
        ).fetchall()
        if len(seq) >= 2:
            result.append((line_norm, region, [tuple(r) for r in seq]))
    return result


_OVERRIDES_PATH = Path('data/subway_pair_overrides.json')


def _apply_overrides(conn) -> int:
    """
    OSM 자동 추출이 불가한 역쌍의 수동 보정 곡선을 적용 (재빌드해도 유지).
    예: 6호선 응암루프 응암↔역촌 — OSM이 왕복 선로를 뭉쳐놔 직접 구간 추출 불가.
    키 형식: "line_norm|region|from_stop_id|to_stop_id" → linestring.
    """
    if not _OVERRIDES_PATH.exists():
        return 0
    data = json.loads(_OVERRIDES_PATH.read_text(encoding='utf-8'))
    rows = []
    for key, ls in data.items():
        parts = key.split('|')
        if len(parts) != 4 or not ls:
            continue
        rows.append((parts[0], parts[1], parts[2], parts[3], ls))
    if rows:
        conn.executemany(
            'INSERT OR REPLACE INTO subway_pair_geom '
            '(line_norm, region, from_stop_id, to_stop_id, linestring) '
            'VALUES (?, ?, ?, ?, ?)',
            rows,
        )
    return len(rows)


def main() -> None:
    t0 = time.time()
    conn = connect()
    try:
        line_map = _load_line_map(conn)
        sequences = _load_route_sequences(conn)

        # 고유 인접 역쌍 수집: key=(line_norm, region, from_stop, to_stop)
        # value=(slng, slat, elng, elat)
        pairs: dict[tuple, tuple] = {}
        for line_norm, region, seq in sequences:
            for (sid, slng, slat), (eid, elng, elat) in zip(seq, seq[1:]):
                if sid == eid:
                    continue
                pairs[(line_norm, region, sid, eid)] = (slng, slat, elng, elat)

        rows = []
        missing = []
        no_keys = set()
        for (line_norm, region, sid, eid), (slng, slat, elng, elat) in pairs.items():
            keys = line_map.get((line_norm, region))
            if not keys:
                no_keys.add((line_norm, region))
                missing.append((line_norm, region, sid, eid))
                continue
            span = max(abs(elng - slng), abs(elat - slat))
            margin = max(_MIN_MARGIN, span * _SPAN_RATIO)
            ls = get_segment_by_keys(keys, slng, slat, elng, elat, margin)
            if ls and _curve_ok(ls, slng, slat, elng, elat):
                rows.append((line_norm, region, sid, eid, ls))
            else:
                missing.append((line_norm, region, sid, eid))

        conn.execute('DELETE FROM subway_pair_geom')
        conn.executemany(
            'INSERT OR REPLACE INTO subway_pair_geom '
            '(line_norm, region, from_stop_id, to_stop_id, linestring) '
            'VALUES (?, ?, ?, ?, ?)',
            rows,
        )
        n_override = _apply_overrides(conn)
        conn.commit()

        # ── 리포트 ──
        total = len(pairs)
        print(f'고유 인접 역쌍: {total}개')
        print(f'곡선 생성: {len(rows)}개 ({len(rows) * 100 // max(total, 1)}%)')
        print(f'곡선 누락: {len(missing)}개')
        print(f'수동 보정(override) 적용: {n_override}개')
        if no_keys:
            print(f'  line_map 키 없음(권역 커버리지 밖): {sorted(no_keys)}')

        # 수도권 주요 노선 커버리지
        print('\n■ 수도권 주요 노선 곡선 커버리지:')
        for ln in ('2호선', '3호선', '4호선', '5호선'):
            done = conn.execute(
                "SELECT COUNT(*) FROM subway_pair_geom WHERE line_norm=? AND region='S-1'",
                (ln,),
            ).fetchone()[0]
            print(f'    {ln}: {done}개 역쌍')
    finally:
        conn.close()

    print(f'\n완료 ({time.time() - t0:.1f}s)')


if __name__ == '__main__':
    main()
