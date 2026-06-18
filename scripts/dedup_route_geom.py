"""
transit_routes 형상 중복 제거 — 같은 노선 구간 linestring이 평균 4.1배 반복 저장됨.

고유 형상을 route_geom(id, ls)에 1번만 보관하고 transit_routes.stepN_geom_id로 참조,
기존 stepN_linestring은 NULL 처리 후 VACUUM → 형상 ~458MB를 ~115MB로(75%↓).

쓰기 경로(app/transit.py collect)는 그대로 stepN_linestring에 기록한다(신규 행은 소량).
읽기(app/detail.py)는 geom_id가 있으면 route_geom JOIN으로 복원, 없으면 linestring 폴백.
→ 스키마 자동 감지라 운영(구 스키마)도 무영향.

로컬 SQLite 전용. 사용법:
  DATABASE_URL= SUPABASE_DB_URL= DB_PATH=/abs/apartment.db python scripts/dedup_route_geom.py
"""
from __future__ import annotations
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from app.db import connect
from app.transit import MAX_STEPS
from config import cfg

STEPS = range(1, MAX_STEPS + 1)


def main():
    if cfg.USE_PG:
        print('!! 운영(Postgres) 모드 — 이 스크립트는 로컬 SQLite 전용. 중단.')
        sys.exit(1)
    print(f'DB: {cfg.DB_PATH}')
    conn = connect()
    conn.isolation_level = None   # 명시적 BEGIN/COMMIT 제어 (VACUUM 위해)
    t0 = time.time()

    # 멱등성: 이미 dedup된 DB면 중단(백업에서 복구 후 재실행 권장).
    has_rg = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='route_geom'").fetchone()
    if has_rg and conn.execute('SELECT COUNT(*) FROM route_geom').fetchone()[0] > 0:
        print('!! route_geom에 이미 데이터 있음 — 재실행 방지 위해 중단.')
        sys.exit(1)

    print('① route_geom 생성 + 고유 형상 적재...')
    conn.execute('BEGIN')
    conn.execute(
        'CREATE TABLE IF NOT EXISTS route_geom ('
        'id INTEGER PRIMARY KEY AUTOINCREMENT, ls TEXT NOT NULL)')
    union = ' UNION ALL '.join(
        f'SELECT step{i}_linestring AS ls FROM transit_routes WHERE step{i}_linestring IS NOT NULL'
        for i in STEPS)
    conn.execute(f'INSERT INTO route_geom(ls) SELECT DISTINCT ls FROM ({union})')
    n_geom = conn.execute('SELECT COUNT(*) FROM route_geom').fetchone()[0]
    conn.execute('COMMIT')
    print(f'   고유 형상 {n_geom:,}개')

    print('② stepN_geom_id 컬럼 추가...')
    for i in STEPS:
        try:
            conn.execute(f'ALTER TABLE transit_routes ADD COLUMN step{i}_geom_id INTEGER')
        except Exception as e:
            print(f'   step{i}_geom_id 추가 스킵 ({e})')

    print('③ ls 임시 인덱스 생성...')
    conn.execute('CREATE INDEX IF NOT EXISTS _tmp_rg_ls ON route_geom(ls)')

    print('④ geom_id 매핑 + linestring NULL 처리 (step별)...')
    conn.execute('BEGIN')
    for i in STEPS:
        conn.execute(
            f'UPDATE transit_routes SET step{i}_geom_id = '
            f'(SELECT id FROM route_geom WHERE ls = transit_routes.step{i}_linestring) '
            f'WHERE step{i}_linestring IS NOT NULL')
        conn.execute(
            f'UPDATE transit_routes SET step{i}_linestring = NULL '
            f'WHERE step{i}_geom_id IS NOT NULL')
        print(f'   step{i} 완료 ({(time.time()-t0):.0f}s)')
    conn.execute('COMMIT')

    print('⑤ 임시 인덱스 제거 + VACUUM (수십 초)...')
    conn.execute('DROP INDEX IF EXISTS _tmp_rg_ls')
    conn.execute('VACUUM')
    conn.close()

    sz = os.path.getsize(cfg.DB_PATH) / 1e6
    print(f'완료: route_geom {n_geom:,}개 | 파일 {sz:.1f} MB ({(time.time()-t0):.0f}s)')


if __name__ == '__main__':
    main()
