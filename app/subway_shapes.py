"""
OSM Overpass에서 다운로드한 수도권 지하철 선형 데이터에서 구간 곡선을 추출.
build_pair_geom.py가 line_map 키 기반(get_segment_by_keys)으로 역쌍 곡선 생성에 사용.

data/subway_shapes_kr.json 이 없으면 조용히 None 반환.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Optional

_SHAPES_PATH = Path('data/subway_shapes_kr.json')
_index: dict[str, list[dict]] | None = None   # normalized_name → [shape, ...]


# ── 이름 정규화 ────────────────────────────────────────────────
_STRIP_PREFIX = re.compile(
    r'(수도권\s*전철|수도권\s*광역급행철도|수도권|서울\s*지하철|서울\s*경전철|'
    r'인천\s*도시철도|부산\s*도시철도|대구\s*도시철도|대전\s*도시철도|경기\s*철도)'
)
_STRIP_DIRECTION = re.compile(r':.*$')          # ": 문산 → 용문" 제거
_STRIP_SPECIAL = re.compile(r'[·\s\-_\(\)\[\]·]')  # 점·공백·특수문자


def _norm(name: str) -> str:
    name = _STRIP_DIRECTION.sub('', name)
    name = _STRIP_PREFIX.sub('', name)
    name = _STRIP_SPECIAL.sub('', name)
    return name.lower()


# ── 데이터 로드 및 인덱스 구축 ─────────────────────────────────
def _load_index() -> dict[str, list[dict]]:
    global _index
    if _index is not None:
        return _index
    _index = {}
    if not _SHAPES_PATH.exists():
        return _index
    shapes = json.loads(_SHAPES_PATH.read_text(encoding='utf-8'))
    for s in shapes:
        key = _norm(s.get('name', ''))
        _index.setdefault(key, []).append(s)
    return _index


_CHAIN_EPS = 1e-6   # way 끝점 일치 판정 허용오차(약 0.1m)


def _chain_ways(ways: list[list[tuple[float, float]]]) -> list[tuple[float, float]]:
    """
    way 조각들을 끝점 매칭으로 순서대로 이어붙여 연속 폴리라인 생성.
    OSM relation의 way가 저장 순서대로면 그냥 concat되지만, 순서가 섞여 있으면
    naive concat은 수 km 텔레포트를 만든다. 가장 긴 way에서 시작해 양방향으로
    끝점이 맞는 way를 (필요시 뒤집어) 붙인다. 연결 안 되는 조각(분기/실제 공백)은
    버린다 → 메인 선형만 남음.
    """
    segs = [w for w in ways if len(w) >= 2]
    if not segs:
        return []
    used = [False] * len(segs)
    start = max(range(len(segs)), key=lambda i: len(segs[i]))
    chain = list(segs[start])
    used[start] = True

    def near(a, b) -> bool:
        return abs(a[0] - b[0]) < _CHAIN_EPS and abs(a[1] - b[1]) < _CHAIN_EPS

    changed = True
    while changed:
        changed = False
        for i, w in enumerate(segs):
            if used[i]:
                continue
            if near(chain[-1], w[0]):
                chain.extend(w[1:])
            elif near(chain[-1], w[-1]):
                chain.extend(reversed(w[:-1]))
            elif near(chain[0], w[-1]):
                chain[:0] = w[:-1]
            elif near(chain[0], w[0]):
                chain[:0] = list(reversed(w))[:-1]
            else:
                continue
            used[i] = True
            changed = True
    return chain


def _flat_pts(shape: dict) -> list[tuple[float, float]]:
    """shape의 way들을 끝점 매칭으로 순서대로 이은 (lng, lat) 리스트 (shape별 메모이즈)."""
    cached = shape.get('_chain')
    if cached is not None:
        return cached
    ways = [[(p['lng'], p['lat']) for p in way] for way in shape.get('ways', [])]
    chain = _chain_ways(ways)
    shape['_chain'] = chain
    return chain


def _dist2(ax: float, ay: float, bx: float, by: float) -> float:
    return (ax - bx) ** 2 + (ay - by) ** 2


def _nearest(pts: list[tuple[float, float]], x: float, y: float) -> int:
    best_i, best_d = 0, float('inf')
    for i, (px, py) in enumerate(pts):
        d = _dist2(px, py, x, y)
        if d < best_d:
            best_d, best_i = d, i
    return best_i


# ── 공개 API ──────────────────────────────────────────────────
_DEFAULT_BBOX_MARGIN = 0.015   # ~1.5km


def _segment_from_candidates(
    candidates: list[dict],
    start_lng: float, start_lat: float,
    end_lng: float,   end_lat: float,
    bbox_margin: float = _DEFAULT_BBOX_MARGIN,
) -> Optional[str]:
    """후보 shape들 중 start/end에 가장 잘 맞고 bbox를 통과하는 구간을 추출."""
    if not candidates:
        return None

    # 허용 bbox: start/end 범위에서 margin 이내만 유효
    min_lng_ok = min(start_lng, end_lng) - bbox_margin
    max_lng_ok = max(start_lng, end_lng) + bbox_margin
    min_lat_ok = min(start_lat, end_lat) - bbox_margin
    max_lat_ok = max(start_lat, end_lat) + bbox_margin

    # 모든 후보를 score 순으로 정렬, bbox 통과하는 첫 번째 사용
    scored: list[tuple] = []
    for shape in candidates:
        pts = _flat_pts(shape)
        if len(pts) < 2:
            continue
        si = _nearest(pts, start_lng, start_lat)
        ei = _nearest(pts, end_lng,   end_lat)
        score = _dist2(*pts[si], start_lng, start_lat) + \
                _dist2(*pts[ei], end_lng,   end_lat)
        scored.append((score, pts, si, ei))

    scored.sort(key=lambda x: x[0])

    for _, pts, si, ei in scored:
        # 구간 슬라이싱 (방향 보정)
        if si <= ei:
            segment = pts[si:ei + 1]
        else:
            segment = pts[ei:si + 1][::-1]

        if len(segment) < 2:
            continue

        # bbox 검증: 분기 노선에서 잘못된 구간 추출 시 bbox 초과 → 다음 후보 시도
        seg_lngs = [p[0] for p in segment]
        seg_lats = [p[1] for p in segment]
        if min(seg_lngs) < min_lng_ok or max(seg_lngs) > max_lng_ok or \
           min(seg_lats) < min_lat_ok or max(seg_lats) > max_lat_ok:
            continue

        return ' '.join(f'{p[0]},{p[1]}' for p in segment)

    return None


def get_segment_by_keys(
    osm_keys: list[str],
    start_lng: float, start_lat: float,
    end_lng: float,   end_lat: float,
    bbox_margin: float = _DEFAULT_BBOX_MARGIN,
) -> Optional[str]:
    """
    line_map이 지정한 OSM 계통 키 목록으로 구간 추출 (노선명 키워드 매칭 우회).
    """
    if not osm_keys:
        return None
    index = _load_index()
    if not index:
        return None
    candidates: list[dict] = []
    for k in osm_keys:
        candidates.extend(index.get(k, []))
    return _segment_from_candidates(
        candidates, start_lng, start_lat, end_lng, end_lat, bbox_margin)
