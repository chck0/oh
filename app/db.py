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
# cfg.USE_PG / cfg.DATABASE_URL / cfg.IS_SERVERLESS 로 중앙 관리
# (하위 호환: 이 모듈을 from app.db import USE_PG 하는 곳은 cfg.USE_PG 로 이전)
USE_PG = cfg.USE_PG  # re-export for backward compat during migration

# pgBouncer 트랜잭션 모드(6543 포트)에서는 prepared statement 비활성 필수
_PG_KWARGS = {'prepare_threshold': None, 'connect_timeout': 5}

# ── 커넥션 풀 ────────────────────────────────────────────────
_pg_pool = None


def _get_pool():
    """psycopg_pool.ConnectionPool 지연 초기화. 실패 시 None 반환(직결 폴백)."""
    global _pg_pool
    if _pg_pool is not None:
        return _pg_pool
    try:
        from psycopg_pool import ConnectionPool

        def _configure(conn):
            # autocommit: 읽기 쿼리가 트랜잭션을 열지 않게 함
            # → 반납 시 INTRANS 롤백 노이즈 제거 + 에러 후 커넥션 오염 방지
            conn.autocommit = True

        _pg_pool = ConnectionPool(
            cfg.DATABASE_URL,
            min_size=1 if cfg.IS_SERVERLESS else 4,
            max_size=int(os.getenv('PG_POOL_MAX', '12')),
            kwargs=_PG_KWARGS,
            configure=_configure,
            timeout=10,        # 풀 고갈 시 대기 한계(초)
            max_idle=300,      # 유휴 커넥션 보존(초)
            open=True,         # min_size 만큼 즉시 워밍
        )
    except Exception as e:
        import logging
        logging.getLogger('app').warning('커넥션 풀 초기화 실패 — 직결 폴백: %s', e)
        _pg_pool = None
    return _pg_pool


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
# ── camelCase 컬럼 자동 인용 (SQLite SQL → Postgres 변환) ────────
# Postgres는 unquoted 식별자를 소문자로 fold하므로 camelCase 컬럼은
# 반드시 큰따옴표로 감싸야 한다.
#
# [동적 로딩 전략]
# 1. _CAMEL_COLS_FALLBACK — 하드코딩된 안전망. DB 없이도 항상 작동.
# 2. refresh_camel_cols(conn) — 앱 시작 시 Postgres information_schema에서
#    실제 카멜케이스 컬럼 목록을 한 번 조회해 _SQL_RE를 재빌드.
#    → 스키마에 컬럼이 추가/변경돼도 코드 수정 없이 자동 반영.

_CAMEL_COLS_FALLBACK = (
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


def _build_sql_re(cols: tuple) -> re.Pattern:
    """camelCase 컬럼 목록으로 SQL 변환용 정규식 재빌드."""
    # 긴 것 먼저 → 짧은 이름이 긴 이름 안에서 잘못 매칭되는 것 방지
    alt = '|'.join(sorted(cols, key=len, reverse=True))
    return re.compile(
        r'"[^"]*"'                       # already-quoted identifier
        r"|'(?:[^']|'')*'"               # string literal
        r'|\?'                            # placeholder
        r'|\b(?:' + alt + r')\b',        # camelCase column
        re.VERBOSE,
    )


# 현재 활성 regex — refresh_camel_cols() 호출 시 교체됨
_SQL_RE: re.Pattern = _build_sql_re(_CAMEL_COLS_FALLBACK)


def refresh_camel_cols(conn) -> None:
    """
    Postgres information_schema에서 카멜케이스 컬럼을 동적 조회해 _SQL_RE 갱신.
    앱 시작 시(lifespan) 1회 호출. 실패해도 폴백 유지 → 무중단.
    """
    global _SQL_RE
    try:
        rows = conn.execute(
            """SELECT DISTINCT column_name
               FROM information_schema.columns
               WHERE table_schema = 'public'
                 AND column_name <> lower(column_name)
               ORDER BY column_name"""
        ).fetchall()
        cols = tuple(r[0] for r in rows)
        if cols:
            _SQL_RE = _build_sql_re(cols)
            import logging
            logging.getLogger('app').info(
                'camelCase 컬럼 %d개 로드 완료 (information_schema)', len(cols)
            )
    except Exception as e:
        import logging
        logging.getLogger('app').warning(
            'camelCase 컬럼 동적 로드 실패 — fallback(%d개) 사용: %s',
            len(_CAMEL_COLS_FALLBACK), e,
        )


def _q_to_pg(sql: str) -> str:
    """SQLite SQL → Postgres SQL 변환 (placeholder + camelCase 컬럼 인용)."""
    def repl(m):
        s = m.group(0)
        if s == '?':
            return '%s'
        if s[0] == '"':
            return s  # 이미 인용된 식별자
        if s[0] == "'":
            return s.replace('%', '%%')  # LIKE '%..%' 안의 % → psycopg3 이스케이프
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
    def __init__(self, conn, pool=None):
        self._c = conn
        self._pool = pool  # 풀에서 빌렸으면 close() 시 반납

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

    def rollback(self):
        try:
            return self._c.rollback()
        except Exception:
            pass

    def close(self):
        # 풀에서 빌린 커넥션은 반납(재사용), 직결이면 실제 종료.
        if self._pool is not None:
            try:
                self._pool.putconn(self._c)
                return
            except Exception:
                pass
        try:
            return self._c.close()
        except Exception:
            pass


# ── 메인 진입점 ──────────────────────────────────────────────
def connect():
    if USE_PG:
        pool = _get_pool()
        if pool is not None:
            raw = pool.getconn()
            return _PgConn(raw, pool=pool)
        # 풀 사용 불가 → 직결 폴백
        import psycopg
        c = psycopg.connect(cfg.DATABASE_URL, **_PG_KWARGS)
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
