"""
SQLite ↔ Postgres 비호환 SQL을 Python 레벨로 끌어올린 헬퍼.

원칙: 런타임 SQL은 두 DB 모두에서 동작하는 portable subset만 사용.
DB별 분기가 꼭 필요한 곳(UPSERT, schema bootstrap 등)만 여기서 처리.
"""
from __future__ import annotations
import os
from datetime import date

USE_PG = bool(os.getenv('DATABASE_URL') or os.getenv('SUPABASE_DB_URL'))


# ── 날짜 헬퍼 ────────────────────────────────────────────────
def year_month_minus(months: int) -> int:
    """N개월 전의 YYYY*100 + MM 정수값 (예: 2026-05 - 3개월 = 202602).
    원래 SQL: CAST(strftime('%Y','now') AS INT)*100 + CAST(strftime('%m','now') AS INT) - 3
    """
    today = date.today()
    y, m = today.year, today.month - months
    while m <= 0:
        y -= 1
        m += 12
    return y * 100 + m


def year_minus(years: int) -> int:
    """N년 전의 YYYY 정수 (예: 2026 - 3 = 2023)."""
    return date.today().year - years


# ── UPSERT 헬퍼 ──────────────────────────────────────────────
def upsert_sql(table: str, cols: list[str], pk_cols: list[str]) -> str:
    """`INSERT OR REPLACE INTO` 의 portable 대체.

    Postgres: INSERT ... ON CONFLICT (...) DO UPDATE SET ...
    SQLite  : INSERT OR REPLACE INTO ...
    """
    placeholders = ','.join(['?'] * len(cols))
    col_list = ','.join(cols)
    if USE_PG:
        update_cols = [c for c in cols if c not in pk_cols]
        set_clause = ', '.join(f'{c}=EXCLUDED.{c}' for c in update_cols)
        pk_clause = ', '.join(pk_cols)
        return (
            f'INSERT INTO {table} ({col_list}) VALUES ({placeholders}) '
            f'ON CONFLICT ({pk_clause}) DO UPDATE SET {set_clause}'
        )
    return f'INSERT OR REPLACE INTO {table} ({col_list}) VALUES ({placeholders})'


# ── INSERT ... RETURNING (lastrowid 대체) ────────────────────
def insert_returning_id(table: str, cols: list[str], id_col: str) -> str:
    """INSERT 후 PK 받기. SQLite는 lastrowid를 별도 사용 (RETURNING 사용 X)."""
    placeholders = ','.join(['?'] * len(cols))
    col_list = ','.join(cols)
    if USE_PG:
        return f'INSERT INTO {table} ({col_list}) VALUES ({placeholders}) RETURNING {id_col}'
    return f'INSERT INTO {table} ({col_list}) VALUES ({placeholders})'


def get_last_id(conn, cursor, table: str, id_col: str):
    """INSERT 직후 PK 추출 — DB별 분기."""
    if USE_PG:
        row = cursor.fetchone()
        return row[0] if row else None
    return cursor.lastrowid


# ── GREATEST 헬퍼 (dual workplace 정렬용) ────────────────────
def greatest(*cols: str) -> str:
    """portable GREATEST(col1, col2, ...).

    Postgres: GREATEST(col1, col2)  — 내장 지원
    SQLite  : MAX(col1, col2)       — 가변 인수 MAX (SQLite 3.1+)
    """
    joined = ', '.join(cols)
    if USE_PG:
        return f'GREATEST({joined})'
    return f'MAX({joined})'


# ── 컬럼 목록 조회 (PRAGMA table_info 대체) ──────────────────
def list_columns(conn, table: str) -> list[str]:
    if USE_PG:
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name=? ORDER BY ordinal_position",
            [table],
        ).fetchall()
        return [r[0] for r in rows]
    rows = conn.execute(f'PRAGMA table_info({table})').fetchall()
    return [r[1] for r in rows]
