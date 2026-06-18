"""
빌드 중간 산출물 테이블을 운영 DB(apartment.db)에서 떼어 별도 파일(geom_build.db)로 이관.

이 테이블들은 서빙 코드(app/main·search·detail·cards·ai)가 전혀 안 읽고,
app/gtfs_subway.py·subway_shapes.py(빌드 전용, scripts에서만 import)에서만 쓰인다.
→ 운영 DB에서 빼도 서빙 무영향. 재베이크가 필요할 때 geom_build.db를 ATTACH해 쓰면 된다.

데이터를 복사(스키마+행) 검증 후 원본에서 DROP + VACUUM → ~220MB 회수.
원본 손상 방지: 카운트 일치 검증 통과 시에만 DROP.

로컬 SQLite 전용. 사용법:
  DATABASE_URL= SUPABASE_DB_URL= DB_PATH=/abs/apartment.db python scripts/split_geom_build.py
"""
from __future__ import annotations
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from app.db import connect
from config import cfg

TABLES = [
    'lane_geom', 'bus_seq_geom', 'line_geom', 'bus_pair_geom', 'subway_pair_geom',
    'gtfs_subway_route', 'gtfs_subway_station', 'gtfs_subway_seq', 'line_map', 'kg_routes',
]
BUILD_DB = str(Path(cfg.DB_PATH).resolve().parent / 'geom_build.db') if not cfg.USE_PG else None


def main():
    if cfg.USE_PG:
        print('!! 운영(Postgres) 모드 — 로컬 SQLite 전용. 중단.')
        sys.exit(1)
    if os.path.exists(BUILD_DB):
        print(f'!! 이미 존재: {BUILD_DB} — 덮어쓰기 방지 위해 중단.')
        sys.exit(1)
    print(f'운영 DB:   {cfg.DB_PATH}')
    print(f'빌드 DB:   {BUILD_DB}')
    conn = connect()
    conn.isolation_level = None
    t0 = time.time()

    conn.execute(f"ATTACH DATABASE '{BUILD_DB}' AS build")

    print('① 스키마+데이터 복사...')
    conn.execute('BEGIN')
    moved = []
    for t in TABLES:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone()
        if not row or not row[0]:
            print(f'   {t}: 없음 — 스킵')
            continue
        # "CREATE TABLE [IF NOT EXISTS] <name>" → "... build.<name>"
        create_build = re.sub(
            r'(?is)^(CREATE TABLE\s+(?:IF NOT EXISTS\s+)?)', r'\1build.', row[0], count=1)
        conn.execute(create_build)
        conn.execute(f'INSERT INTO build."{t}" SELECT * FROM main."{t}"')
        moved.append(t)
    conn.execute('COMMIT')

    print('② 카운트 검증 (운영 == 빌드)...')
    ok = True
    for t in moved:
        nm = conn.execute(f'SELECT COUNT(*) FROM main."{t}"').fetchone()[0]
        nb = conn.execute(f'SELECT COUNT(*) FROM build."{t}"').fetchone()[0]
        flag = 'OK' if nm == nb else '!! 불일치'
        if nm != nb:
            ok = False
        print(f'   {t:22} 운영 {nm:>7} / 빌드 {nb:>7}  {flag}')
    if not ok:
        print('!! 카운트 불일치 — 원본 DROP 안 함. geom_build.db 삭제 후 재시도 요망.')
        conn.execute('DETACH build')
        conn.close()
        sys.exit(1)

    print('③ 운영 DB에서 DROP + VACUUM...')
    for t in moved:
        conn.execute(f'DROP TABLE "{t}"')
    conn.execute('DETACH build')
    conn.execute('VACUUM')
    conn.close()

    main_sz = os.path.getsize(cfg.DB_PATH) / 1e6
    build_sz = os.path.getsize(BUILD_DB) / 1e6
    print(f'완료: 이관 {len(moved)}개 | 운영 {main_sz:.1f} MB / 빌드 {build_sz:.1f} MB '
          f'({time.time()-t0:.0f}s)')


if __name__ == '__main__':
    main()
