"""
OpenStreetMap Overpass API로 수도권 지하철 전 노선 선형 데이터 다운로드.
결과: data/subway_shapes.json

사용법:
    python scripts/download_subway_shapes.py
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

OVERPASS_URL = 'https://overpass-api.de/api/interpreter'
OUT_PATH = Path('data/subway_shapes.json')

# 수도권 전철 노선 쿼리 (subway + light_rail 모두 포함)
QUERY = """
[out:json][timeout:120];
(
  relation["route"="subway"]["type"="route"];
  relation["route"="light_rail"]["type"="route"];
  relation["route"="train"]["network"~"수도권|Seoul|Korail|경의|경춘|경강|서해|동해|공항"]["type"="route"];
);
(._; >;);
out geom;
""".strip()


def fetch_overpass(query: str, retry: int = 3) -> dict:
    from urllib.parse import urlencode
    data = urlencode({'data': query}).encode('utf-8')
    req = Request(OVERPASS_URL, data=data, headers={
        'Content-Type': 'application/x-www-form-urlencoded',
        'User-Agent': 'BADUGI-SubwayShapeDownloader/1.0',
        'Accept': 'application/json',
    })
    for attempt in range(retry):
        try:
            with urlopen(req, timeout=150) as r:
                return json.loads(r.read().decode('utf-8'))
        except URLError as e:
            print(f'  시도 {attempt+1}/{retry} 실패: {e}')
            if attempt < retry - 1:
                time.sleep(5)
    raise RuntimeError('Overpass API 호출 실패')


def build_shapes(raw: dict) -> list[dict]:
    """OSM raw → 노선별 좌표 배열 리스트"""
    # way_id → geometry 좌표 목록 맵
    way_geom: dict[int, list] = {}
    for el in raw.get('elements', []):
        if el['type'] == 'way' and 'geometry' in el:
            way_geom[el['id']] = [{'lat': p['lat'], 'lng': p['lon']} for p in el['geometry']]

    shapes = []
    for el in raw.get('elements', []):
        if el['type'] != 'relation':
            continue
        tags = el.get('tags', {})
        name  = tags.get('name', '')
        ref   = tags.get('ref', '')
        color = tags.get('colour', tags.get('color', ''))
        network = tags.get('network', '')
        route = tags.get('route', '')

        # 방향별 중복 제거용 대표 키 (ref + from→to 없이 노선명 기준)
        coords: list[list] = []
        for member in el.get('members', []):
            if member['type'] == 'way':
                wid = member['ref']
                if wid in way_geom:
                    coords.append(way_geom[wid])

        if not coords:
            continue

        shapes.append({
            'id':      el['id'],
            'name':    name,
            'ref':     ref,
            'color':   color,
            'network': network,
            'route':   route,
            'ways':    coords,   # [[{lat,lng}, ...], ...]
        })

    return shapes


def main():
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    print('Overpass API 쿼리 중... (최대 2분 소요)')
    t0 = time.time()
    raw = fetch_overpass(QUERY)
    elapsed = time.time() - t0
    print(f'  완료 ({elapsed:.1f}s) — 엘리먼트 {len(raw.get("elements", []))}개')

    shapes = build_shapes(raw)
    print(f'  노선(relation) {len(shapes)}개 파싱 완료')

    # 노선명/ref 목록 출력
    for s in sorted(shapes, key=lambda x: x['ref']):
        total_pts = sum(len(w) for w in s['ways'])
        print(f"  [{s['ref']:>8}] {s['name'][:40]:<40} ways={len(s['ways'])} pts={total_pts}")

    OUT_PATH.write_text(json.dumps(shapes, ensure_ascii=False, indent=2), encoding='utf-8')
    size_kb = OUT_PATH.stat().st_size // 1024
    print(f'\n저장 완료: {OUT_PATH} ({size_kb:,} KB)')


if __name__ == '__main__':
    main()
