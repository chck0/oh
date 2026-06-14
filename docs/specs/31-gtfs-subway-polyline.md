# Spec 31: GTFS 기반 지하철 폴리라인 (GTFS 순서 + OSM 곡선)

> 상태: Draft → Implemented | 작성일: 2026-06-14 | 브랜치: chck0527

## 1. Why (왜)

- **문제:** 현재 지하철 폴리라인은 OSM 선형을 "승차역→하차역 전체 구간" 단위로 nearest-point 매칭해서 추출 → 분기 노선(5호선 등)에서 엉뚱한 갈래를 골라 **선이 꼬임**. 임시로 bbox 검증을 넣어 꼬임은 막았지만, bbox 실패 시 곡선이 통째로 사라짐(역 좌표 직선 fallback).
- **사용자가 얻는 것:** 지도에서 아파트 클릭 시 지하철 경로가 **분기 꼬임 없이 + 실제 선로 곡선으로** 정확하게 그려짐.
- **핵심 아이디어:** KTDB GTFS(2024.3)가 노선을 **방향·분기·권역별로 분리**해 깨끗한 정차 순서를 제공 → 이걸 backbone으로 쓰고, **인접 역쌍마다** OSM 곡선을 붙여 이어 만든다. 인접 역쌍 단위에선 분기 모호성이 없어 OSM 매칭이 안 꼬임.

## 2. Scope (범위)

- **포함:**
  - GTFS 원본(routes/stops/stop_times) 정제 → SQLite 테이블 적재 (지하철 route_type=1만)
  - GTFS 노선 ↔ OSM 계통 키 **명시적 정합(line_map, 1:N)** + 커버리지 리포트
  - 인접 역쌍별 OSM 곡선 사전 생성 (`subway_pair_geom`)
  - `transit_routes.step*_linestring` 재backfill (역쌍 곡선 이어붙임)
  - 검증: API 응답 + apt 11140-15 (5호선 포함) 꼬임 없음
- **제외(안 함):**
  - 버스 폴리라인 (현행 ODsay 직선 유지)
  - 운영 Supabase 실시간 partial-search 경로 적용 (후속 — 우선 baked 경로만)
  - shapes.txt 활용 (KTDB 미구축, 데이터 없음)

## 3. 설계 (어떻게)

### 데이터 흐름 (오프라인 빌드 → baked 런타임)

```
원본 GTFS(1.6GB) ─┐
                  ├─① build_gtfs_subway.py → 테이블 ①②③
OSM subway_shapes ┘
                   ─② reconcile_lines.py   → line_map (GTFS↔OSM 계통 1:N) + 리포트
                   ─③ build_pair_geom.py    → subway_pair_geom (역쌍 OSM 곡선)
                   ─④ backfill              → transit_routes.step*_linestring (이어붙임)
홈페이지 런타임 = transit_routes만 읽음 (지금과 동일, 빠름)
```

### 건드리는 파일 (신규 스크립트 + 모듈)

- `scripts/build_gtfs_subway.py` (신규): GTFS 정제 → 테이블 ①②③
- `scripts/reconcile_lines.py` (신규): 노선 정합 → line_map + 미매칭 리포트
- `scripts/build_pair_geom.py` (신규): 역쌍 OSM 곡선 → subway_pair_geom
- `scripts/backfill_linestring.py` (확장 또는 신규 `backfill_pair_geom.py`): 역쌍 곡선 이어붙여 step_linestring 재생성
- `app/subway_shapes.py`: `get_segment()` 재사용 (역쌍 단위 호출). 필요 시 역쌍 전용 헬퍼 추가
- `scripts/migrate_gtfs_subway.sql` (신규): 테이블 DDL

### DB 변경 (`scripts/migrate_gtfs_subway.sql`)

```sql
gtfs_subway_station(stop_id PK, name, name_norm, lng, lat)
gtfs_subway_route(route_id PK, line_name, line_norm, region, direction, desc)
gtfs_subway_seq(route_id, seq, stop_id, PK(route_id,seq))
subway_pair_geom(line_norm, region, from_stop_id, to_stop_id, linestring,
                 PK(line_norm,region,from_stop_id,to_stop_id))
line_map(gtfs_line_norm, gtfs_region, osm_line_key, verified)   -- 1:N
```

- 모두 **로컬 SQLite(apartment.db)** 에 적재. `download_db.py` 재다운로드 시 날아가므로 **빌드 스크립트는 멱등**(DROP/CREATE or INSERT OR REPLACE).
- `transit_routes` 스키마는 그대로 (step*_linestring 값만 갱신).

### API 변경

- 없음. `/api/apt/{seq}/routes` 응답 구조 동일, linestring 품질만 향상.

### 핵심 로직 / 엣지케이스

- **stop_times.txt(1.6GB):** 노선당 대표 1회차(`_Ord001`)만 스트리밍 필터 → 메모리 안전.
- **line_map 1:N:** GTFS `1호선`+`S-1` → OSM `1호선경부선계통`,`1호선경인선계통`… 여러 후보. 역쌍 곡선 생성 시 모든 후보 중 bbox 통과하는 것 채택.
- **권역 구분:** GTFS `S-1`(수도권)/`S-2`(부산)로 동명 노선 분리.
- **매칭 실패 역쌍:** 임시 직선으로 덮지 않고 **리포트로 남김** → 원인(이름/커버리지/좌표)별로 line_map·alias 개선. 진짜 OSM에 없는 노선만 최후로 직선 fallback.
- **ODsay step ↔ GTFS 정합:** step의 ODsay 역 좌표를 GTFS 역에 nearest-point 스냅 → GTFS 순서로 역쌍 분해.
- **금지:** os.getenv 직접 호출(→cfg), SQL f-string(→? 바인딩), 운영 Supabase 직접 접속, filter_path 등 비즈니스 로직 변경.

## 4. 완료 조건 (Acceptance Criteria)

- [ ] AC1: `migrate_gtfs_subway.sql` 적용 → 5개 테이블 생성
- [ ] AC2: `build_gtfs_subway.py` → gtfs_subway_route 145개·station ~1288개·seq 적재 (멱등)
- [ ] AC3: `reconcile_lines.py` → line_map 적재 + 미매칭 GTFS 노선 수 리포트(0 또는 사유 명시)
- [ ] AC4: `build_pair_geom.py` → subway_pair_geom 적재 + 곡선 누락 역쌍 로그
- [ ] AC5: backfill → transit_routes 지하철 step이 역쌍 곡선 이어붙인 linestring 보유
- [ ] AC6: `/api/apt/11140-15/routes` (wp_id=3,7) 지하철 선이 **꼬임 없이 곡선** (5호선 포함 육안 확인 가능)
- [ ] AC7: 기존 테스트(`python -m pytest`) 통과
- [ ] 로컬(SQLite) 동작 / Vercel(Supabase) 실시간 경로는 후속(baked 경로는 동작)
