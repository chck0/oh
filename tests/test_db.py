"""
app/db.py 단위 테스트

- _q_to_pg  : SQLite '?' → Postgres '%s' + camelCase 컬럼 큰따옴표 처리
- _RowProxy : dict-like 행 접근 (int 인덱스 / 문자열 키 / get / keys 등)
"""
import pytest
from app.db import _q_to_pg, _RowProxy


# ── _q_to_pg ──────────────────────────────────────────────────

class TestQToPg:
    def test_single_placeholder(self):
        assert _q_to_pg('SELECT * FROM t WHERE id = ?') == \
               'SELECT * FROM t WHERE id = %s'

    def test_multiple_placeholders(self):
        result = _q_to_pg('INSERT INTO t (a, b) VALUES (?, ?)')
        assert result.count('%s') == 2
        assert '?' not in result

    def test_no_placeholder_unchanged(self):
        sql = 'SELECT id, address_key FROM workplaces'
        assert _q_to_pg(sql) == sql

    def test_camel_case_column_gets_double_quoted(self):
        result = _q_to_pg('SELECT kaptCode FROM apartments')
        assert '"kaptCode"' in result

    def test_string_literal_preserved(self):
        sql = "SELECT * FROM t WHERE name = 'hello'"
        result = _q_to_pg(sql)
        assert "'hello'" in result

    def test_placeholder_and_camel_together(self):
        sql = 'SELECT kaptCode FROM apartments WHERE wp_id = ?'
        result = _q_to_pg(sql)
        assert '"kaptCode"' in result
        assert '%s' in result
        assert '?' not in result

    def test_double_quoted_literal_preserved(self):
        # 이미 큰따옴표로 감싼 식별자는 그대로 통과
        sql = 'SELECT "kaptCode" FROM apartments'
        result = _q_to_pg(sql)
        assert '"kaptCode"' in result


# ── _RowProxy ─────────────────────────────────────────────────

class TestRowProxy:
    def _row(self):
        return _RowProxy((1, 'hello', 37.5), ['wp_id', 'address', 'lat'])

    def test_int_index_first(self):
        assert self._row()[0] == 1

    def test_int_index_last(self):
        assert self._row()[2] == 37.5

    def test_string_key_access(self):
        assert self._row()['address'] == 'hello'

    def test_get_existing_key(self):
        assert self._row().get('wp_id') == 1

    def test_get_missing_key_default(self):
        assert self._row().get('nonexistent', 'fallback') == 'fallback'

    def test_get_missing_key_none_default(self):
        assert self._row().get('nonexistent') is None

    def test_contains_true(self):
        assert 'lat' in self._row()

    def test_contains_false(self):
        assert 'missing' not in self._row()

    def test_keys(self):
        assert self._row().keys() == ['wp_id', 'address', 'lat']

    def test_len(self):
        assert len(self._row()) == 3

    def test_iter_yields_values(self):
        assert list(self._row()) == [1, 'hello', 37.5]
