"""
GTFS 순서 + OSM 역쌍 곡선을 이어붙여 지하철 step의 고품질 linestring 생성 (Spec 31).

레퍼런스 테이블(gtfs_subway_station/route/seq, subway_pair_geom)을 한 번 메모리에 적재.
build_subway_linestring(): ODsay 승차/하차 좌표 → GTFS 역 스냅 → 순서대로 역쌍 곡선 이어붙임.
곡선 없는 역쌍은 역 좌표 직선으로 메움. 매칭 실패 시 None(호출측이 ODsay 원본 유지).
"""
from __future__ import annotations
from typing import Optional

from app.db import connect
from app.subway_shapes import _norm

# ── 메모리 인덱스 (lazy) ───────────────────────────────────────
_stations: dict[str, tuple[float, float]] | None = None      # stop_id → (lng, lat)
_line_routes: dict[str, list[tuple]] | None = None           # line_norm → [(route_id, region, [stop_id,...])]
_line_pts: dict[str, list[tuple]] | None = None              # line_norm → [(stop_id, lng, lat)]
_pair: dict[tuple, str] | None = None                        # (line_norm, region, a, b) → linestring


def _load() -> None:
    global _stations, _line_routes, _line_pts, _pair
    if _stations is not None:
        return
    _stations, _line_routes, _line_pts, _pair = {}, {}, {}, {}
    conn = connect()
    try:
        for stop_id, lng, lat in conn.execute(
            'SELECT stop_id, lng, lat FROM gtfs_subway_station'
        ):
            _stations[stop_id] = (lng, lat)

        # 노선별 정차 순서
        routes = conn.execute(
            'SELECT route_id, line_norm, region FROM gtfs_subway_route'
        ).fetchall()
        for route_id, line_norm, region in routes:
            seq = [r[0] for r in conn.execute(
                'SELECT stop_id FROM gtfs_subway_seq WHERE route_id=? ORDER BY seq',
                (route_id,),
            )]
            if len(seq) < 2:
                continue
            _line_routes.setdefault(line_norm, []).append((route_id, region, seq))
            pts = _line_pts.setdefault(line_norm, [])
            seen = {p[0] for p in pts}
            for sid in seq:
                if sid not in seen and sid in _stations:
                    lng, lat = _stations[sid]
                    pts.append((sid, lng, lat))
                    seen.add(sid)

        for line_norm, region, a, b, ls in conn.execute(
            'SELECT line_norm, region, from_stop_id, to_stop_id, linestring '
            'FROM subway_pair_geom'
        ):
            _pair[(line_norm, region, a, b)] = ls
    finally:
        conn.close()


def _nearest_station(line_norm: str, lng: float, lat: float) -> Optional[str]:
    pts = _line_pts.get(line_norm)
    if not pts:
        return None
    best_id, best_d = None, float('inf')
    for sid, plng, plat in pts:
        d = (plng - lng) ** 2 + (plat - lat) ** 2
        if d < best_d:
            best_d, best_id = d, sid
    return best_id


def _find_route(line_norm: str, board: str, alight: str) -> Optional[tuple]:
    """board·alight를 모두 포함하는 노선 변형 중 가장 직접적(역 수 최소)인 것."""
    best = None
    best_gap = float('inf')
    for route_id, region, seq in _line_routes.get(line_norm, []):
        try:
            ib = seq.index(board)
            ia = seq.index(alight)
        except ValueError:
            continue
        gap = abs(ia - ib)
        if gap < best_gap and gap > 0:
            best_gap = gap
            # 항상 board→alight 방향의 sub-seq
            sub = seq[ib:ia + 1] if ib <= ia else seq[ia:ib + 1][::-1]
            best = (region, sub)
    return best


def _pair_points(line_norm: str, region: str, a: str, b: str) -> list[tuple[float, float]]:
    """역쌍 곡선 → [(lng,lat),...]. 없으면 두 역 좌표 직선."""
    ls = _pair.get((line_norm, region, a, b))
    if ls:
        return [(float(x), float(y)) for x, y in (p.split(',') for p in ls.split())]
    rev = _pair.get((line_norm, region, b, a))
    if rev:
        pts = [(float(x), float(y)) for x, y in (p.split(',') for p in rev.split())]
        return pts[::-1]
    # 직선 fallback
    pa, pb = _stations.get(a), _stations.get(b)
    if pa and pb:
        return [pa, pb]
    return []


def build_subway_linestring(
    line_name: str,
    board_lng: float, board_lat: float,
    alight_lng: float, alight_lat: float,
) -> Optional[str]:
    """
    지하철 step → GTFS 순서 + OSM 역쌍 곡선 스티칭 linestring.
    매칭 실패 시 None (호출측이 ODsay 원본 linestring 유지).
    """
    _load()
    line_norm = _norm(line_name or '')
    if not line_norm:
        return None

    board = _nearest_station(line_norm, board_lng, board_lat)
    alight = _nearest_station(line_norm, alight_lng, alight_lat)
    if not board or not alight or board == alight:
        return None

    found = _find_route(line_norm, board, alight)
    if not found:
        return None
    region, sub = found

    out: list[tuple[float, float]] = []
    for a, b in zip(sub, sub[1:]):
        pts = _pair_points(line_norm, region, a, b)
        if not pts:
            continue
        if out and pts and out[-1] == pts[0]:
            out.extend(pts[1:])
        else:
            out.extend(pts)

    if len(out) < 2:
        return None
    return ' '.join(f'{lng},{lat}' for lng, lat in out)
