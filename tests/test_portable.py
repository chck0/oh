"""
app/portable.py 순수 함수 테스트

- year_month_minus, year_minus : 날짜 계산
- upsert_sql, insert_returning_id : SQL 생성 (SQLite / PG 분기)
"""
from datetime import date
import pytest
import app.portable as portable
from unittest.mock import MagicMock
from app.portable import (
    year_month_minus,
    year_minus,
    upsert_sql,
    insert_returning_id,
    get_last_id,
    list_columns,
    USE_PG,
)


# ── 날짜 헬퍼 ─────────────────────────────────────────────────

class TestYearMonthMinus:
    def test_zero_months_equals_today(self):
        today = date.today()
        expected = today.year * 100 + today.month
        assert year_month_minus(0) == expected

    def test_result_is_valid_yyyymm(self):
        result = year_month_minus(3)
        year = result // 100
        month = result % 100
        assert 2000 <= year <= 2100
        assert 1 <= month <= 12

    def test_month_wraps_across_january(self):
        today = date.today()
        # 현재 월보다 더 많이 빼면 반드시 전년도로 넘어간다
        result = year_month_minus(today.month + 1)
        assert result // 100 < today.year

    def test_twelve_months_ago_is_last_year_same_month(self):
        today = date.today()
        result = year_month_minus(12)
        assert result // 100 == today.year - 1
        assert result % 100 == today.month

    def test_result_decreases_with_more_months(self):
        r1 = year_month_minus(1)
        r3 = year_month_minus(3)
        assert r3 < r1


class TestYearMinus:
    def test_zero_years_is_current_year(self):
        assert year_minus(0) == date.today().year

    def test_three_years(self):
        assert year_minus(3) == date.today().year - 3

    def test_result_type_is_int(self):
        assert isinstance(year_minus(1), int)


# ── upsert_sql ────────────────────────────────────────────────

class TestUpsertSql:
    def test_sqlite_contains_insert_or_replace(self, monkeypatch):
        monkeypatch.setattr(portable, 'USE_PG', False)
        sql = upsert_sql('transit_cache', ['origin_cell', 'wp_id', 'total_time'], ['origin_cell', 'wp_id'])
        assert 'INSERT OR REPLACE INTO transit_cache' in sql

    def test_sqlite_placeholder_count_matches_cols(self, monkeypatch):
        monkeypatch.setattr(portable, 'USE_PG', False)
        cols = ['a', 'b', 'c']
        sql = upsert_sql('t', cols, ['a'])
        assert sql.count('?') == len(cols)

    def test_pg_contains_on_conflict(self, monkeypatch):
        monkeypatch.setattr(portable, 'USE_PG', True)
        sql = upsert_sql('transit_cache', ['origin_cell', 'wp_id', 'total_time'], ['origin_cell', 'wp_id'])
        assert 'ON CONFLICT' in sql
        assert 'DO UPDATE SET' in sql

    def test_pg_update_excludes_pk_cols(self, monkeypatch):
        monkeypatch.setattr(portable, 'USE_PG', True)
        sql = upsert_sql('t', ['pk_col', 'data_col'], ['pk_col'])
        assert 'data_col=EXCLUDED.data_col' in sql
        assert 'pk_col=EXCLUDED.pk_col' not in sql

    def test_pg_pk_in_conflict_clause(self, monkeypatch):
        monkeypatch.setattr(portable, 'USE_PG', True)
        sql = upsert_sql('t', ['a', 'b', 'c'], ['a', 'b'])
        assert 'ON CONFLICT (a, b)' in sql

    def test_table_name_in_sql(self):
        sql = upsert_sql('workplaces', ['col_a'], ['col_a'])
        assert 'workplaces' in sql


# ── insert_returning_id ───────────────────────────────────────

class TestInsertReturningId:
    def test_sqlite_no_returning_clause(self, monkeypatch):
        monkeypatch.setattr(portable, 'USE_PG', False)
        sql = insert_returning_id('workplaces', ['address_key', 'b_code'], 'wp_id')
        assert 'INSERT INTO workplaces' in sql
        assert 'RETURNING' not in sql

    def test_sqlite_placeholder_count(self, monkeypatch):
        monkeypatch.setattr(portable, 'USE_PG', False)
        cols = ['a', 'b', 'c']
        sql = insert_returning_id('t', cols, 'id')
        assert sql.count('?') == len(cols)

    def test_pg_has_returning(self, monkeypatch):
        monkeypatch.setattr(portable, 'USE_PG', True)
        sql = insert_returning_id('workplaces', ['address_key', 'b_code'], 'wp_id')
        assert 'RETURNING wp_id' in sql

    def test_pg_table_name_in_sql(self, monkeypatch):
        monkeypatch.setattr(portable, 'USE_PG', True)
        sql = insert_returning_id('workplaces', ['x'], 'wp_id')
        assert 'workplaces' in sql


# ── get_last_id ───────────────────────────────────────────────

class TestGetLastId:
    def test_sqlite_returns_lastrowid(self, monkeypatch):
        monkeypatch.setattr(portable, 'USE_PG', False)
        mock_cursor = MagicMock()
        mock_cursor.lastrowid = 42
        result = get_last_id(None, mock_cursor, 'workplaces', 'wp_id')
        assert result == 42

    def test_pg_fetchone_returns_first_column(self, monkeypatch):
        monkeypatch.setattr(portable, 'USE_PG', True)
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (99,)
        result = get_last_id(None, mock_cursor, 'workplaces', 'wp_id')
        assert result == 99

    def test_pg_fetchone_none_returns_none(self, monkeypatch):
        monkeypatch.setattr(portable, 'USE_PG', True)
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        result = get_last_id(None, mock_cursor, 'workplaces', 'wp_id')
        assert result is None


# ── list_columns ──────────────────────────────────────────────

class TestListColumns:
    def test_sqlite_returns_list(self, mem_db, monkeypatch):
        monkeypatch.setattr(portable, 'USE_PG', False)
        cols = list_columns(mem_db, 'workplaces')
        assert isinstance(cols, list)

    def test_sqlite_contains_known_columns(self, mem_db, monkeypatch):
        monkeypatch.setattr(portable, 'USE_PG', False)
        cols = list_columns(mem_db, 'workplaces')
        assert 'wp_id' in cols
        assert 'address_key' in cols
        assert 'lat' in cols

    def test_pg_path_uses_information_schema(self, monkeypatch):
        monkeypatch.setattr(portable, 'USE_PG', True)
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            ('col_a',), ('col_b',),
        ]
        cols = list_columns(mock_conn, 'test_table')
        assert cols == ['col_a', 'col_b']
