# scripts/ — 데이터 파이프라인

번호 순서대로 실행. 각 스크립트는 멱등(재실행 안전)하도록 작성.

## 실행 순서

| # | 스크립트 | 입력 | 출력 (DB 테이블) |
|---|---|---|---|
| 01 | fetch_kapt_complexes.py | MOLIT API | kapt_complexes |
| 02 | fetch_apartments_v4.py | MOLIT API + kapt_complexes | apartments |
| 03 | geocode.py | apartments.kaptAddr | apartments.lat/lng |
| 04 | fetch_trade_recent.py | MOLIT API | trade_recent |
| 05 | fetch_trade_history.py | MOLIT API | trade_history |
| 06 | fetch_building_register.py | MOLIT API + kapt_complexes | building_register |
| 07 | supplement_no_data.py | 카카오 + MOLIT | building_register |
| 08 | classify_buildings.py | building_register | apartments.is_apt, building_type |
| 10 | reset_transit_tables.py | — | transit_cache, transit_routes |
| 11 | fetch_transit.py | ODsay (직장 좌표 입력) | transit_cache |
| 12 | load_transit_routes.py | transit_cache | transit_routes |

## 새 단계 추가 시

기존 번호 사이 (예: 05와 06 사이) 끼우려면 `055_xxx.py` 사용 — 글로브 정렬 유지됨.
