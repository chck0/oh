"""
DB 연결 헬퍼 — Supabase(Postgres) / 로컬 SQLite 듀얼 어댑터

DATABASE_URL(또는 SUPABASE_DB_URL) 환경변수가 있으면 psycopg3로 Supabase 연결,
없으면 기존 로컬 SQLite(data/apartment.db)를 그대로 사용.

API 호환:
    conn.execute(sql, params).fetchone() / .fetchall()
    conn.executemany(sql, seq)
    conn.commit() / conn.close()
    row['col'], row[i], 'col' in row.keys(), row.get('col') 모두 지원

런타임 코드가 두 DB에서 동시에 동작하도록, '?' 플레이스홀더는 어댑터가
자동으로 '%s'(Postgres)로 변환. SQLite 전용 함수(strftime, printf 등)는
이미 portable.py 헬퍼로 빼서 SQL에서 제거됨.
"""
import os
import re
import sqlite3
from contextlib import contextmanager
from config import cfg

# ── Supabase 전환 스위치 ──────────────────────────────────────
DATABASE_URL = os.getenv('DATABASE_URL') or os.getenv('SUPABASE_DB_URL') or ''
USE_PG = bool(DATABASE_URL)

# pgBouncer 트랜잭션 모드(6543 포트)에서는 prepared statement 비활성 필수
_PG_KWARGS = {'prepare_threshold': None}


# ── sqlite3.Row 호환 행 프록시 (Postgres / libSQL 공통) ───────
class _RowProxy:
    """row[i], row['col'], 'col' in row.keys(), row.get('col') 모두 지원."""
    __slots__ = ('_t', '_keys')

    def __init__(self, values, keys):
        self._t = tuple(values)
        self._keys = keys

    def __getitem__(self, k):
        if isinstance(k, int):
            return self._t[k]
        return self._t[self._keys.index(k)]

    def get(self, k, default=None):
        try:
            return self._t[self._keys.index(k)]
        except (ValueError, IndexError):
            return default

    def keys(self):
        return list(self._keys)

    def __contains__(self, k):
        return k in self._keys

    def __iter__(self):
        return iter(self._t)

    def __len__(self):
        return len(self._t)


# ── '?' → '%s' 변환 (문자열 리터럴 보호) ─────────────────────
_PLACEHOLDER_RE = re.compile(r"""
    '(?:[^']|'')*'        # single-quoted literal (anything between, escaped '')
    |                     # OR
    \?                    # 변환 대상
""", re.VERBOSE)

def _q_to_pg(sql: str) -> str:
    def repl(m):
        s = m.group(0)
        return '%s' if s == '?' else s
    return _PLACEHOLDER_RE.sub(repl, sql)


# ── psycopg 커서 / 커넥션 래퍼 ────────────────────────────────
class _PgCursor:
    def __init__(self, cur):
        self._cur = cur

    def _keys(self):
        return [c.name for c in (self._cur.description or [])]

    def fetchone(self):
        r = self._cur.fetchone()
        return None if r is None else _RowProxy(r, self._keys())

    def fetchall(self):
        ks = self._keys()
        return [_RowProxy(r, ks) for r in self._cur.fetchall()]

    @property
    def lastrowid(self):
        # Postgres엔 lastrowid 없음 → INSERT 시 RETURNING으로 받아야 함
        # workplaces.py가 사용 — 거기서 RETURNING wp_id로 명시 처리
        return None

    def __iter__(self):
        return iter(self.fetchall())


class _PgConn:
    def __init__(self, conn):
        self._c = conn

    def execute(self, sql, params=()):
        cur = self._c.cursor()
        cur.execute(_q_to_pg(sql), tuple(params) if params else None)
        return _PgCursor(cur)

    def executemany(self, sql, seq):
        cur = self._c.cursor()
        cur.executemany(_q_to_pg(sql), [tuple(p) for p in seq])
        return _PgCursor(cur)

    def commit(self):
        return self._c.commit()

    def close(self):
        try:
            return self._c.close()
        except Exception:
            pass


# ── 메인 진입점 ──────────────────────────────────────────────
def connect():
    if USE_PG:
        import psycopg
        c = psycopg.connect(DATABASE_URL, **_PG_KWARGS)
        return _PgConn(c)

    conn = sqlite3.connect(cfg.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db_session():
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


# FastAPI dependency
def get_db():
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()
