"""
SQLite(data/apartment.db) → Supabase(Postgres) 데이터 이관

전제:
    1. supabase_schema.sql 을 Supabase SQL Editor에서 미리 실행해 스키마 생성
    2. .env (또는 환경변수)에 DATABASE_URL 세팅 (Supabase 'Direct connection' 사용 권장 - 5432 포트)
       예: postgresql://postgres:[PWD]@db.[PROJECT-REF].supabase.co:5432/postgres
       (이관 시에는 pgBouncer 6543 포트 말고 5432 직접 연결을 권장 - COPY/대량 INSERT 안전)
    3. pip install psycopg[binary] python-dotenv

실행:
    python scripts/migrate_sqlite_to_supabase.py

옵션:
    --only=workplaces,apartments    # 특정 테이블만 이관
    --skip=trade_history            # 일부 제외
    --batch=2000                    # 배치 크기 (default 1000)
    --truncate                      # 이관 전 대상 테이블 비우기
"""
from __future__ import annotations
import sys, os, sqlite3, argparse, time
from pathlib import Path

# Windows cp949 콘솔에서 UTF-8 출력 강제 (em-dash 등 인코딩 에러 방지)
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# 프로젝트 루트의 .env 로드
sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')

try:
    import psycopg
except ImportError:
    print("psycopg가 설치되지 않았습니다.  pip install 'psycopg[binary]'")
    sys.exit(1)


SQLITE_PATH = os.getenv('DB_PATH', 'data/apartment.db')
if not os.path.isabs(SQLITE_PATH):
    SQLITE_PATH = str(Path(__file__).parent.parent / SQLITE_PATH)

PG_URL = os.getenv('DATABASE_URL') or os.getenv('SUPABASE_DB_URL')
if not PG_URL:
    print("DATABASE_URL 환경변수가 없습니다. .env에 추가하세요.")
    sys.exit(1)

# 이관 대상 테이블 (의존 순서대로)
TABLES = [
    'workplaces',
    'apartments',
    'kapt_complexes',
    'trade_recent',
    'trade_history',
    'apt_walking_poi',
    'apt_hsmp_mapping',
    'apt_slope',
    'grid_cells',
    'transit_cache',
    'transit_routes',
    'apt_friend_comment',
    'apt_pt_friend_comment',
    'building_register',
    'building_register_log',
]


def quote_ident(name: str) -> str:
    # camelCase/한글 컬럼은 큰따옴표로 감싸야 안전
    if name.isidentifier() and name.islower():
        return name
    return f'"{name}"'


def migrate_table(sl: sqlite3.Connection, pg, table: str, batch: int, truncate: bool):
    # 1) SQLite에 테이블 존재 확인
    if not sl.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone():
        print(f'  [{table}] SQLite에 없음 - 스킵')
        return

    # 2) 컬럼 목록 (SQLite 기준 - Postgres와 동일해야 함)
    cols = [r[1] for r in sl.execute(f'PRAGMA table_info({table})').fetchall()]
    if not cols:
        print(f'  [{table}] 컬럼 없음 - 스킵')
        return

    # apt_walking_poi.id 같은 AUTOINCREMENT는 Postgres에선 SERIAL -
    # SQLite의 기존 id값을 그대로 보존하려면 그대로 넣고, 마지막에 sequence reset.
    quoted_cols = [quote_ident(c) for c in cols]
    placeholders = ','.join(['%s'] * len(cols))
    insert_sql = (
        f'INSERT INTO {table} ({", ".join(quoted_cols)}) '
        f'VALUES ({placeholders})'
    )

    # 3) 총 행수
    total = sl.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
    if total == 0:
        print(f'  [{table}] 0행 - 스킵')
        return

    with pg.cursor() as cur:
        if truncate:
            cur.execute(f'TRUNCATE TABLE {table} RESTART IDENTITY CASCADE')
            pg.commit()
            print(f'  [{table}] TRUNCATE 완료')

        t0 = time.time()
        sent = 0
        # SQLite는 메모리 효율 위해 chunk fetch
        cursor = sl.execute(f'SELECT {", ".join(cols)} FROM {table}')
        while True:
            chunk = cursor.fetchmany(batch)
            if not chunk:
                break
            cur.executemany(insert_sql, chunk)
            sent += len(chunk)
            print(f'    {sent}/{total} ({sent*100//total}%)', end='\r')
        pg.commit()
        print(f'  [{table}] {sent}행 / {time.time()-t0:.1f}s')

    # 4) SERIAL/Identity 시퀀스 보정 (workplaces.wp_id, apt_walking_poi.id 등)
    _fix_sequence(pg, table)


def _fix_sequence(pg, table: str):
    """INSERT 후 SERIAL 컬럼의 nextval이 max(id)+1이 되도록 보정."""
    serial_map = {
        'workplaces':     ('wp_id', 'workplaces_wp_id_seq'),
        'apt_walking_poi': ('id', 'apt_walking_poi_id_seq'),
    }
    if table not in serial_map:
        return
    col, seq = serial_map[table]
    with pg.cursor() as cur:
        cur.execute(
            f"SELECT setval(%s, COALESCE((SELECT MAX({col}) FROM {table}), 1), true)",
            (seq,),
        )
    pg.commit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', help='쉼표 구분 - 이 테이블만 이관')
    ap.add_argument('--skip', help='쉼표 구분 - 이 테이블 제외')
    ap.add_argument('--batch', type=int, default=1000)
    ap.add_argument('--truncate', action='store_true',
                    help='이관 전 대상 테이블 TRUNCATE')
    args = ap.parse_args()

    targets = list(TABLES)
    if args.only:
        only = {t.strip() for t in args.only.split(',')}
        targets = [t for t in targets if t in only]
    if args.skip:
        skip = {t.strip() for t in args.skip.split(',')}
        targets = [t for t in targets if t not in skip]

    print(f'SQLite : {SQLITE_PATH}')
    print(f'Postgres: {PG_URL.split("@")[-1]}')
    print(f'테이블  : {", ".join(targets)}')
    print()

    sl = sqlite3.connect(SQLITE_PATH)
    # prepare_threshold=None - Supabase Free의 6543 Transaction pooler 호환
    # (5432 Direct/Session pooler면 굳이 필요 없지만 켜둬도 무해)
    pg = psycopg.connect(PG_URL, prepare_threshold=None)
    try:
        for t in targets:
            print(f'→ {t}')
            migrate_table(sl, pg, t, args.batch, args.truncate)
    finally:
        sl.close()
        pg.close()

    print('\n완료.')


if __name__ == '__main__':
    main()
