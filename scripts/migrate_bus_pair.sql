-- 버스 정류장 쌍 도로 라우팅 캐시 (Spec 32)
-- 무방향 쌍: a < b (좌표 문자열 정렬)로 정규화 저장. 백필 시 방향 맞춰 뒤집어 사용.
CREATE TABLE IF NOT EXISTS bus_pair_geom (
    a          TEXT,   -- "lng,lat" 정류장1 (정렬상 작은 쪽)
    b          TEXT,   -- "lng,lat" 정류장2
    linestring TEXT,   -- 도로 라우팅 결과 "lng,lat lng,lat ..." (a→b 방향)
    status     TEXT,   -- pending | ok | straight | fail
    PRIMARY KEY (a, b)
);
CREATE INDEX IF NOT EXISTS idx_bus_pair_status ON bus_pair_geom(status);
