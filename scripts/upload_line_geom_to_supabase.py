"""
geom_build.db의 line_geom(2,993행, ~48MB)을 Supabase에 업로드.
이미 존재하면 DROP 후 재생성.

사용법:
  python scripts/upload_line_geom_to_supabase.py
"""
import os, sqlite3, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import psycopg
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / '.env')

GEOM_DB  = Path('data/geom_build.db')
BATCH    = 100

def main():
    # Supabase URL: SUPABASE_DB_URL 우선, 없으면 DATABASE_URL (postgresql:// 형식)
    url = os.getenv('SUPABASE_DB_URL') or os.getenv('DATABASE_URL', '')
    if not url.startswith('postgresql'):
        print('ERROR: SUPABASE_DB_URL 또는 postgresql:// 형식의 DATABASE_URL 필요')
        return

    # 로컬 SQLite에서 읽기
    sc = sqlite3.connect(GEOM_DB)
    rows = sc.execute(
        "SELECT line_id, class, ls, status FROM line_geom WHERE status='ok' AND ls IS NOT NULL"
    ).fetchall()
    sc.close()
    print(f'로컬 line_geom: {len(rows):,}행 로드')

    # Supabase 연결
    conn = psycopg.connect(url, prepare_threshold=None)
    cur = conn.cursor()

    # 테이블 생성 (이미 있으면 교체)
    cur.execute('DROP TABLE IF EXISTS line_geom')
    cur.execute('''
        CREATE TABLE line_geom (
            line_id TEXT NOT NULL,
            class   INTEGER NOT NULL,
            ls      TEXT NOT NULL,
            status  TEXT NOT NULL DEFAULT 'ok'
        )
    ''')
    cur.execute('CREATE INDEX idx_line_geom_id_class ON line_geom(line_id, class)')
    conn.commit()
    print('테이블 생성 완료')

    # 배치 INSERT
    t0 = time.time()
    for i in range(0, len(rows), BATCH):
        batch = rows[i:i+BATCH]
        cur.executemany(
            'INSERT INTO line_geom (line_id, class, ls, status) VALUES (%s, %s, %s, %s)',
            batch
        )
        if (i // BATCH) % 10 == 0:
            conn.commit()
            pct = (i + len(batch)) / len(rows) * 100
            print(f'  {i+len(batch):,}/{len(rows):,}행 ({pct:.0f}%) — {time.time()-t0:.0f}s')

    conn.commit()
    conn.close()
    print(f'완료: {len(rows):,}행 업로드 ({time.time()-t0:.0f}s)')


if __name__ == '__main__':
    main()
