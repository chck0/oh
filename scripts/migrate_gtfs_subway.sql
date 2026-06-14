-- GTFS 기반 지하철 폴리라인 레퍼런스 테이블 (2026-06-14, Spec 31)
-- 로컬 SQLite(apartment.db)에 적재. 빌드 스크립트가 멱등하게 재적재.

-- ① 지하철 역 (GTFS stops.txt → RS_ 역)
CREATE TABLE IF NOT EXISTS gtfs_subway_station (
    stop_id   TEXT PRIMARY KEY,
    name      TEXT,
    name_norm TEXT,
    lng       REAL,
    lat       REAL
);

-- ② 지하철 노선 변형 (GTFS routes.txt → route_type=1)
CREATE TABLE IF NOT EXISTS gtfs_subway_route (
    route_id   TEXT PRIMARY KEY,
    line_name  TEXT,   -- 서울 4호선
    line_norm  TEXT,   -- 4호선 (도시 prefix 제거)
    region     TEXT,   -- S-1(수도권) / S-2(부산) ...
    direction  TEXT,   -- D / U
    descr      TEXT    -- 진접-사당
);

-- ③ 노선별 역 순서 (GTFS stop_times.txt → 노선당 대표 1회차)
CREATE TABLE IF NOT EXISTS gtfs_subway_seq (
    route_id TEXT,
    seq      INTEGER,
    stop_id  TEXT,
    PRIMARY KEY (route_id, seq)
);

-- ④ 역쌍별 OSM 곡선 (build_pair_geom.py가 적재)
CREATE TABLE IF NOT EXISTS subway_pair_geom (
    line_norm    TEXT,
    region       TEXT,
    from_stop_id TEXT,
    to_stop_id   TEXT,
    linestring   TEXT,   -- "lng,lat lng,lat ..." OSM 곡선
    PRIMARY KEY (line_norm, region, from_stop_id, to_stop_id)
);

-- ⑤ GTFS 노선 ↔ OSM 계통 키 매핑 (reconcile_lines.py가 적재, 1:N)
CREATE TABLE IF NOT EXISTS line_map (
    gtfs_line_norm TEXT,
    gtfs_region    TEXT,
    osm_line_key   TEXT,
    verified       INTEGER DEFAULT 0,
    PRIMARY KEY (gtfs_line_norm, gtfs_region, osm_line_key)
);

CREATE INDEX IF NOT EXISTS idx_gtfs_seq_stop ON gtfs_subway_seq(stop_id);
CREATE INDEX IF NOT EXISTS idx_gtfs_route_line ON gtfs_subway_route(line_norm, region);
CREATE INDEX IF NOT EXISTS idx_pair_line ON subway_pair_geom(line_norm, region);
