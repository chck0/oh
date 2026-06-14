"""
OSM Overpass에서 다운로드한 수도권 지하철 선형 데이터로
ODsay 경로의 지하철 구간 linestring을 고품질로 교체.

data/subway_shapes_kr.json 이 없으면 조용히 None 반환 (기존 동작 유지).
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


# ODsay 노선명 → OSM 검색 키워드 (일부 이름이 달라 보완)
_ALIASES: dict[str, list[str]] = {
    '경의중앙선':   ['경의중앙'],
    '수인분당선':   ['수인분당', '수인·분당', '분당'],
    '경춘선':       ['경춘'],
    '경강선':       ['경강'],
    '서해선':       ['서해'],
    '공항철도':     ['공항철도', 'arex', '공항'],
    '신림선':       ['신림'],
    '우이신설선':   ['우이신설', '우이'],
    '의정부경전철': ['의정부'],
    '용인경전철':   ['용인경전철', '에버라인'],
    '김포골드라인': ['김포골드', '김포'],
    'gtxa':         ['gtx-a', 'gtxa'],
}


def _keywords(line_name: str) -> list[str]:
    n = _norm(line_name)
    if n in _ALIASES:
        return _ALIASES[n]
    return [n]


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
def get_segment(
    line_name: str,
    start_lng: float, start_lat: float,
    end_lng: float,   end_lat: float,
) -> Optional[str]:
    """
    ODsay 지하철 구간 → OSM 선형에서 해당 구간 추출.
    반환: "경도,위도 경도,위도 ..." 또는 None (매칭 실패 시)
    """
    if not line_name:
        return None

    index = _load_index()
    if not index:
        return None

    keywords = _keywords(line_name)

    # 후보 수집
    candidates: list[dict] = []
    for key, shapes in index.items():
        if any(kw in key for kw in keywords):
            candidates.extend(shapes)

    if not candidates:
        return None

    # 허용 bbox: start/end 범위에서 margin 이내만 유효 (~1.5km 고정)
    bbox_margin = 0.015
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


def enrich_linestring(step_type: str, line_name: str, existing_ls: Optional[str]) -> Optional[str]:
    """
    지하철 step의 기존 linestring을 OSM 고품질 선형으로 교체.
    - 지하철이 아니거나 OSM 매칭 실패 시 existing_ls 그대로 반환.
    """
    if step_type not in ('지하철',):
        return existing_ls
    if not existing_ls:
        return existing_ls

    pts_str = existing_ls.strip().split()
    if len(pts_str) < 2:
        return existing_ls

    try:
        slng, slat = map(float, pts_str[0].split(','))
        elng, elat = map(float, pts_str[-1].split(','))
    except ValueError:
        return existing_ls

    result = get_segment(line_name, slng, slat, elng, elat)
    return result if result else existing_ls
