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


# ── SQL 어댑터 (PG 모드 한정) ─────────────────────────────────
# Postgres는 unquoted identifier를 lowercase로 fold함. 스키마(supabase_schema.sql)
# 에선 camelCase 컬럼을 큰따옴표로 case 보존했는데, 앱 코드 SQL은 unquoted라
# `a.kaptCode` → `a.kaptcode` lookup으로 깨짐. 알려진 camelCase 컬럼만 골라
# 자동으로 `"..."`로 감싸 해결.
_CAMEL_COLS = (
    'kaptCode', 'kaptName', 'kaptAddr', 'doroJuso', 'kaptdaCnt',
    'ktownFlrNo', 'kaptBaseFloor', 'kaptMparea60', 'kaptMparea85',
    'kaptMparea135', 'kaptMparea136', 'kaptBcompany', 'kaptdPcnt',
    'kaptdPcntu', 'kaptdCccnt', 'groundElChargerCnt',
    'undergroundElChargerCnt', 'codeAptNm',
    'bjdCode', 'codeSaleNm', 'codeHeatNm', 'codeMgrNm', 'codeHallNm',
    'kaptUsedate', 'hoCnt', 'kaptDongCnt', 'kaptTopFloor', 'kaptdEcntp',
    'kaptTarea', 'kaptMarea', 'privArea', 'kaptAcompany', 'kaptTel',
    'kaptFax', 'kaptUrl', 'codeMgr', 'kaptMgrCnt', 'kaptCcompany',
    'codeSec', 'kaptdScnt', 'kaptdSecCom', 'codeClean', 'kaptdClcnt',
    'codeGarbage', 'codeDisinf', 'kaptdDcnt', 'disposalType', 'codeStr',
    'kaptdEcapa', 'codeEcon', 'codeEmgr', 'codeFalarm', 'codeWsupply',
    'codeElev', 'kaptdEcnt', 'codeNet', 'welfareFacility',
    'kaptdWtimebus', 'subwayLine', 'subwayStation', 'kaptdWtimesub',
    'convenientFacility', 'educationFacility', 'useYn',
    'mgmBldrgstPk', 'dongNm', 'mainPurpsCdNm', 'etcPurps', 'hhldCnt',
    'grndFlrCnt', 'ugrndFlrCnt', 'totArea', 'archArea', 'platArea',
    'bcRat', 'vlRat', 'strctCdNm', 'useAprDay',
)
# 긴 것 먼저 → 짧은 이름이 긴 이름 안에서 잘못 매칭되는 것 방지
_CAMEL_ALT = '|'.join(sorted(_CAMEL_COLS, key=len, reverse=True))

# 한 번의 regex pass로:
#   1) 이미 큰따옴표로 묶인 identifier ("...") → 그대로
#   2) 작은따옴표 문자열 리터럴 ('...') → 그대로
#   3) ? → %s
#   4) camelCase 컬럼명 (word boundary) → "..."
_SQL_RE = re.compile(
    r'"[^"]*"'                           # already-quoted identifier
    r"|'(?:[^']|'')*'"                   # string literal
    r'|\?'                                # placeholder
    r'|\b(?:' + _CAMEL_ALT + r')\b',     # camelCase column
    re.VERBOSE,
)

def _q_to_pg(sql: str) -> str:
    def repl(m):
        s = m.group(0)
        if s == '?':
            return '%s'
        if s[0] in ('"', "'"):
            return s  # 이미 quoted거나 리터럴
        return f'"{s}"'  # camelCase 컬럼명 → 큰따옴표로
    return _SQL_RE.sub(repl, sql)


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
