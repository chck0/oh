"""
GTFS(KTDB 2024.3) 지하철 데이터 정제 → SQLite 레퍼런스 테이블 적재 (Spec 31, US-001)

원본:
  data/2025-TM-PT-GTFS 대중교통GTFS(2024년 기준)/202403_GTFS_DataSet/
    routes.txt    — route_type=1(도시철도) 노선
    stops.txt     — RS_ 지하철 역
    stop_times.txt — (1.6GB) 노선당 _Ord001 대표회차만 스트리밍 필터

적재 테이블: gtfs_subway_route, gtfs_subway_station, gtfs_subway_seq
멱등: 매 실행마다 해당 테이블을 DELETE 후 재적재.

사용법:
    python scripts/migrate_gtfs_subway.sql 적용 후
    python scripts/build_gtfs_subway.py
"""
from __future__ import annotations
import csv
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from app.db import connect
from app.subway_shapes import _norm

GTFS_DIR = Path('data/2025-TM-PT-GTFS 대중교통GTFS(2024년 기준)/202403_GTFS_DataSet')
SUBWAY_ROUTE_TYPE = '1'   # 도시철도/경전철

# route_id 예: RR_ACC1_S-1-4-4D → region=S-1, 분기/방향 끝의 D/U
_REGION_RE = re.compile(r'_(S-\d+)-')
_DIRECTION_RE = re.compile(r'([DU])$')
# line_norm 산출 시 제거할 도시 prefix (region은 route_id로 따로 보존)
_CITY_PREFIX_RE = re.compile(r'^(수도권|서울|부산|대구|인천|대전|광주|경기|울산)\s*')


def _parse_region(route_id: str) -> str:
    m = _REGION_RE.search(route_id)
    return m.group(1) if m else ''


def _parse_direction(route_id: str) -> str:
    m = _DIRECTION_RE.search(route_id)
    return m.group(1) if m else ''


def _line_norm(route_short_name: str) -> str:
    stripped = _CITY_PREFIX_RE.sub('', route_short_name or '')
    return _norm(stripped)


def load_routes(conn) -> dict[str, str]:
    """routes.txt → gtfs_subway_route 적재. 반환: {route_id: route_short_name}"""
    path = GTFS_DIR / 'routes.txt'
    rows = []
    with path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for r in reader:
            if r.get('route_type') != SUBWAY_ROUTE_TYPE:
                continue
            route_id = r['route_id']
            short = r.get('route_short_name', '') or ''
            long = r.get('route_long_name', '') or ''
            rows.append((
                route_id,
                short,
                _line_norm(short),
                _parse_region(route_id),
                _parse_direction(route_id),
                long,
            ))
    conn.execute('DELETE FROM gtfs_subway_route')
    conn.executemany(
        'INSERT INTO gtfs_subway_route '
        '(route_id, line_name, line_norm, region, direction, descr) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        rows,
    )
    return {row[0]: row[1] for row in rows}


def load_stops(conn) -> None:
    """stops.txt → gtfs_subway_station 적재 (RS_ 역만)."""
    path = GTFS_DIR / 'stops.txt'
    rows = []
    with path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for r in reader:
            stop_id = r['stop_id']
            if not stop_id.startswith('RS'):
                continue
            try:
                lat = float(r['stop_lat'])
                lng = float(r['stop_lon'])
            except (ValueError, KeyError):
                continue
            name = r.get('stop_name', '') or ''
            rows.append((stop_id, name, _norm(name), lng, lat))
    conn.execute('DELETE FROM gtfs_subway_station')
    conn.executemany(
        'INSERT OR REPLACE INTO gtfs_subway_station '
        '(stop_id, name, name_norm, lng, lat) VALUES (?, ?, ?, ?, ?)',
        rows,
    )
    return len(rows)


def load_sequences(conn, route_ids: list[str]) -> tuple[int, list[str]]:
    """
    stop_times.txt 스트리밍 → 노선당 '정차 최다' 트립(전구간 운행) stop 순서 수집.
    _Ord001은 단축운행일 수 있어(예: 7호선 _Ord001=12역 vs 전구간=53역) 노선 일부만
    담길 위험이 있으므로, 해당 노선의 모든 트립 중 정차역이 가장 많은 트립을 대표로 쓴다.
    반환: (적재 행 수, 시퀀스 없는 route_id 목록)
    """
    route_set = set(route_ids)
    # trip_id → [(seq, stop_id), ...]  (RR 철도 트립만 메모리 보관, ~수십만행)
    trip_stops: dict[str, list[tuple[int, str]]] = {}

    path = GTFS_DIR / 'stop_times.txt'
    with path.open(encoding='utf-8-sig', newline='') as f:
        f.readline()  # 헤더 스킵
        for line in f:
            if not line.startswith('RR'):   # 버스 등 빠른 스킵
                continue
            parts = line.rstrip('\n').split(',')
            if len(parts) < 5:
                continue
            trip_id = parts[0]
            rid = trip_id.rsplit('_Ord', 1)[0]
            if rid not in route_set:
                continue
            try:
                seq = int(parts[4])
            except ValueError:
                continue
            trip_stops.setdefault(trip_id, []).append((seq, parts[3]))

    # 노선별 정차 최다 트립 선택
    best: dict[str, tuple[int, str]] = {}   # rid → (정차수, trip_id)
    for trip_id, stops in trip_stops.items():
        rid = trip_id.rsplit('_Ord', 1)[0]
        if rid not in best or len(stops) > best[rid][0]:
            best[rid] = (len(stops), trip_id)

    seq_rows: list[tuple] = []
    for rid, (_, trip_id) in best.items():
        for seq, stop_id in sorted(trip_stops[trip_id]):
            seq_rows.append((rid, seq, stop_id))

    conn.execute('DELETE FROM gtfs_subway_seq')
    conn.executemany(
        'INSERT OR REPLACE INTO gtfs_subway_seq (route_id, seq, stop_id) '
        'VALUES (?, ?, ?)',
        seq_rows,
    )
    missing = [rid for rid in route_ids if rid not in best]
    return len(seq_rows), missing


def main() -> None:
    if not GTFS_DIR.exists():
        print(f'GTFS 디렉토리 없음: {GTFS_DIR}')
        sys.exit(1)

    t0 = time.time()
    conn = connect()
    try:
        route_map = load_routes(conn)
        route_ids = list(route_map.keys())
        print(f'① gtfs_subway_route: {len(route_ids)}개 노선 적재')

        n_stops = load_stops(conn)
        print(f'② gtfs_subway_station: {n_stops}개 역 적재')

        print('③ gtfs_subway_seq: stop_times.txt 스트리밍 중 (1.6GB, 수십 초)...')
        n_seq, missing = load_sequences(conn, route_ids)
        print(f'③ gtfs_subway_seq: {n_seq}행 적재 ({len(route_ids) - len(missing)}개 노선)')
        if missing:
            print(f'   ⚠ 시퀀스 없는 노선 {len(missing)}개: {missing[:10]}')

        conn.commit()
    finally:
        conn.close()

    print(f'완료 ({time.time() - t0:.1f}s)')


if __name__ == '__main__':
    main()
