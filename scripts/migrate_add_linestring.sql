-- transit_routes에 폴리라인 좌표 컬럼 추가 (2026-06-14)
-- ODsay passShape.linestring 값을 저장 — "경도,위도 경도,위도 ..." 공백 구분 문자열
ALTER TABLE transit_routes ADD COLUMN step1_linestring TEXT;
ALTER TABLE transit_routes ADD COLUMN step2_linestring TEXT;
ALTER TABLE transit_routes ADD COLUMN step3_linestring TEXT;
ALTER TABLE transit_routes ADD COLUMN step4_linestring TEXT;
ALTER TABLE transit_routes ADD COLUMN step5_linestring TEXT;
