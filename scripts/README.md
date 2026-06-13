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

## 로컬 데모 모드 (spec-30)

API 키·운영 데이터 없이 전체 화면 플로우를 로컬에서 확인:

```bash
bash scripts/run_demo.sh
# → http://localhost:8000/ 에서 '강남역' 검색
```

- `seed_demo_data.py`: 강남역(wp_id=1) 기준 가상 단지 10곳 시드 (멱등, SQLite 전용)
- `BADUGI_DEMO=1`: 시드된 직장은 Kakao 호출 없이 DB에서 반환 (미설정 시 운영과 동일)
- 친구 코멘트 사전 시드 → ANTHROPIC 키 불필요. 채팅·신규 주소는 실제 키 필요.
