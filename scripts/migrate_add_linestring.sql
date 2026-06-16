-- transit_routes에 폴리라인 좌표 컬럼 추가 (2026-06-14)
-- 경로 step별 형상 "경도,위도 경도,위도 ..." 공백 구분 문자열을 저장.
-- /api/apt/{apt_seq}/routes 응답에 포함 → 지도에 경로 선 렌더링.
ALTER TABLE transit_routes ADD COLUMN step1_linestring TEXT;
ALTER TABLE transit_routes ADD COLUMN step2_linestring TEXT;
ALTER TABLE transit_routes ADD COLUMN step3_linestring TEXT;
ALTER TABLE transit_routes ADD COLUMN step4_linestring TEXT;
ALTER TABLE transit_routes ADD COLUMN step5_linestring TEXT;
