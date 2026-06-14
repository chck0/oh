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


def _flat_pts(shape: dict) -> list[tuple[float, float]]:
    """shape의 모든 way를 순서대로 합친 (lng, lat) 리스트"""
    pts: list[tuple[float, float]] = []
    for way in shape.get('ways', []):
        for p in way:
            pts.append((p['lng'], p['lat']))
    return pts


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
