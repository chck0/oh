# Spec 32: 버스 경로 도로 라우팅 (OSRM)

> 상태: In Progress | 작성일: 2026-06-14 | 브랜치: chck0527
> ⚠️ 진행 중 작업 — 컨텍스트 압축 시 이 문서가 단일 진실원본(SSOT). 재개 시 먼저 읽을 것.

## 1. Why
버스 경로가 지금 **정류장 직선 연결**(건물 가로지름). 지하철처럼 **도로 따라가는 곡선**으로.
목표: **전체 + 100%**, 미리 계산해 DB에 baked → 런타임은 읽기만 (지하철과 동일 철학).

## 2. 핵심 통찰 — 버스는 지하철보다 단순
지하철 고생(노선명 정규화·중복 stop_id·단축운행·계통 매칭)은 전부 "형상 매칭" 때문. 버스는
**좌표를 도로에 라우팅만** 함 → 노선번호 겹침("146")·이름·stop_id 문제 **전부 무관**.

## 3. 규모 (측정 완료, transit_routes 기준)
- 버스 step 전체: **52,762**
- 고유 시퀀스: 16,433
- **고유 무방향 정류장 쌍: 13,306 ← 실제 라우팅 횟수** (쌍이 시퀀스보다 적음 = 도로 공유)
- 2점짜리(중간정류장 없음): 556
- → **쌍 단위 캐시**가 정답 (재사용·조합 → 미래 검색도 커버 = 사실상 100%, subway_pair_geom과 동일)

## 4. 설계
- 라우팅 엔진: **로컬 OSRM 자체 호스팅** (무료·무제한·오프라인). 13,306 쌍은 몇 분.
- `bus_pair_geom` 캐시 테이블: (정류장쌍 좌표키) → 도로 linestring
- backfill: 버스 step 정류장 → 인접 쌍 분해 → bus_pair_geom 조회·이어붙임 (subway backfill_pair_geom과 동일 구조)
- 검증 `_route_ok`: detour 비율 + 내부 점프 → 실패는 직선 fallback + 로그
- **운영(Vercel) OSRM 불가 → 빌드타임 오프라인 → baked만 운영** (지하철과 동일)
- **프론트는 변경 불필요**: result.html drawRoutePolylines가 이미 simplify+smooth로 곡선 렌더 → baked 버스곡선 자동 반영

## 5. 리스크 레지스터 (처음부터 박을 안전장치)
| 상황 | 대응 |
|---|---|
| OSRM 경로 없음(code≠Ok) | 직선 fallback + 로그 |
| 정류장 엉뚱한 도로 snap | detour 비율 검증 초과시 직선 |
| 차경로≠버스경로(일방통행·전용차로) | 쌍 단위라 대부분 OK, detour 컷 |
| via U턴 페널티 | 쌍 단위 라우팅(per-pair)이라 무관 |
| 2점짜리 step 556개 | 라우팅하되 detour 엄격 |
| **lng/lat 순서** (OSRM은 lng,lat) | 명시 주의 — 지하철때도 함정 |
| **멱등성**: 라우팅된 선 재라우팅 | raw JSON에서 정류장 읽기(안정) OR 점개수 가드 |
| 재실행 16k 반복 | dedup 캐시 → 재실행 캐시 히트만 |

## 6. Phase
0. **OSRM 셋업** (진행 중): Docker(켜짐) + `ghcr.io/project-osrm/osrm-backend` pull + Geofabrik `south-korea-latest.osm.pbf` 다운 → osrm-extract(-p car.lua) → osrm-partition → osrm-customize → osrm-routed --algorithm mld -p 5000. 작업폴더 `.tmp/osrm`. 디스크 5GB OK(~3-4GB 필요).
1. `scripts/migrate_bus_pair.sql`: bus_pair_geom 테이블
2. `scripts/build_bus_pairs.py`: transit_routes 버스 step에서 고유 무방향 쌍 추출
3. `scripts/route_bus_pairs.py`: 각 쌍 OSRM(localhost:5000) 라우팅 + _route_ok 검증 → bus_pair_geom 적재 (실패 직선+로그)
4. `scripts/backfill_bus_geom.py`: 버스 step linestring을 쌍 이어붙여 교체 (raw JSON 기반, subway 패턴)
5. 검증: 라우팅 성공률·우회거부 집계 + 지도 스팟체크. 목표 100%.

## 7. 현재 상태 (재개 지점)
- ✅ PoC 성공: 버스 150번, 공개 OSRM 데모, 직선 3.67km → 도로 89점 3.78km (`.tmp/bus150_routed.json`)
- ✅ Docker Desktop 켜짐(데몬 정상), C: 11GB 여유 / 5GB 사용 허가
- 🔄 OSRM 이미지 pull 시작됨 (백그라운드)
- ⬜ south-korea pbf 다운로드 → OSRM 처리 → 서버 기동
- ⬜ Phase 1~5

## 8. 제약 (CLAUDE.md)
cfg 사용 / ? 바인딩 / app.db connect / 하드코딩 금지 / 로컬 SQLite만. OSRM URL은 config.py에 추가.

## 9. 완료 조건
- bus_pair_geom 13,306 쌍 라우팅(검증 통과분) + 실패 로그
- transit_routes 버스 step이 도로 곡선 보유
- 지도에서 버스선이 도로 따라 그려짐 (지하철처럼)
- 라우팅 실패/직선 fallback 비율 집계 = 숫자로 확인
