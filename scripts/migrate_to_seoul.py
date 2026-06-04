"""
Supabase 리전 이전: Tokyo → Seoul 데이터 마이그레이션.

사용법:
    # 1) Seoul 프로젝트의 'Direct connection' 문자열 (포트 5432) 사용 권장.
    #    pgBouncer(6543, transaction mode)는 COPY 스트리밍에 부적합.
    set OLD_DB_URL=postgresql://...tokyo... (포트 5432 직결)
    set NEW_DB_URL=postgresql://...seoul... (포트 5432 직결)
    python scripts/migrate_to_seoul.py

동작:
    1. NEW DB에 scripts/supabase_schema.sql 적용 (CREATE TABLE IF NOT EXISTS)
    2. 각 테이블을 COPY (BINARY) 스트리밍으로 Tokyo → Seoul 복사
    3. 행 수 검증

주의:
    - NEW DB의 기존 데이터를 TRUNCATE 후 재적재 (재실행 안전).
    - 외래키가 없으므로 테이블 순서 무관.
"""
import os
import sys
import time
import pathlib

import psycopg

# Windows 콘솔(cp949)에서 한글/기호 출력 시 크래시 방지
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')  # type: ignore[union-attr]
except Exception:
    pass

OLD_URL = os.getenv('OLD_DB_URL')
NEW_URL = os.getenv('NEW_DB_URL')
SCHEMA_FILE = pathlib.Path(__file__).parent / 'supabase_schema.sql'

# 이전 대상 테이블 (의존성 없음 → 순서 무관)
TABLES = [
    'workplaces', 'apartments', 'kapt_complexes',
    'trade_recent', 'trade_history', 'trade_tags',
    'apt_walking_poi', 'apt_hsmp_mapping', 'apt_slope',
    'grid_cells', 'transit_cache', 'transit_routes',
    'apt_friend_comment', 'apt_pt_friend_comment',
    'building_register', 'building_register_log',
]

_KW = {'prepare_threshold': None, 'connect_timeout': 15}


def _count(conn, t):
    try:
        return conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
    except Exception:
        return -1


def main():
    if not OLD_URL or not NEW_URL:
        sys.exit('OLD_DB_URL / NEW_DB_URL 환경변수를 설정하세요 (포트 5432 직결 권장).')

    print('→ Tokyo(OLD) 연결...')
    old = psycopg.connect(OLD_URL, **_KW)
    print('→ Seoul(NEW) 연결...')
    new = psycopg.connect(NEW_URL, **_KW)
    # autocommit: 실패한 쿼리(없는 테이블 COUNT 등)가 트랜잭션을 오염시켜
    # 후속 쿼리를 전부 실패시키는 것을 방지.
    old.autocommit = True
    new.autocommit = True

    # 1) 스키마 적용
    print(f'→ 스키마 적용: {SCHEMA_FILE.name}')
    ddl = SCHEMA_FILE.read_text(encoding='utf-8')
    with new.cursor() as cur:
        cur.execute(ddl)
    new.commit()
    print('  스키마 OK')

    # 2) 테이블별 COPY 스트리밍
    grand = time.monotonic()
    for t in TABLES:
        src_n = _count(old, t)
        if src_n < 0:
            print(f'  [SKIP] {t} — OLD에 없음')
            continue
        t0 = time.monotonic()
        # 멱등성: 기존 데이터 비우기
        with new.cursor() as cur:
            cur.execute(f'TRUNCATE TABLE {t} CASCADE')
        new.commit()

        # 컬럼 목록을 소스/대상에서 각각 받아 교집합만 사용 (순서·drift 안전)
        src_cols = [r[0] for r in old.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name=%s AND table_schema='public' ORDER BY ordinal_position",
            (t,),
        ).fetchall()]
        dst_cols = {r[0] for r in new.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name=%s AND table_schema='public'",
            (t,),
        ).fetchall()}
        cols = [c for c in src_cols if c in dst_cols]
        collist = ', '.join(f'"{c}"' for c in cols)

        # COPY ... TO STDOUT (CSV) → COPY ... FROM STDIN (CSV) 스트리밍
        # BINARY는 프레이밍 어긋나면 hang. CSV+명시 컬럼이 견고.
        with old.cursor().copy(f'COPY {t} ({collist}) TO STDOUT (FORMAT CSV)') as src_copy:
            with new.cursor().copy(f'COPY {t} ({collist}) FROM STDIN (FORMAT CSV)') as dst_copy:
                for block in src_copy:
                    dst_copy.write(block)
        new.commit()

        dst_n = _count(new, t)
        dt = time.monotonic() - t0
        ok = '[OK]' if dst_n == src_n else '[XX MISMATCH]'
        print(f'  {ok} {t}: {src_n:,} -> {dst_n:,}  ({dt:.1f}s)', flush=True)

    print(f'\n전체 완료: {time.monotonic()-grand:.1f}s')
    old.close()
    new.close()


if __name__ == '__main__':
    main()
