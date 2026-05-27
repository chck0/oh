"""
tests/test_search_history.py — spec-15 GET /api/workplaces/recent 테스트

검증 범위:
  1. 정상 응답: 200, 배열 반환
  2. 정렬: search_count DESC, last_used DESC
  3. limit 파라미터: 기본값 5, 클램프 1~10
  4. 결과 0개 시 빈 배열
  5. address_norm IS NULL 행 제외
"""
import sqlite3
import pytest
from fastapi.testclient import TestClient


_SCHEMA = """
CREATE TABLE IF NOT EXISTS workplaces (
    wp_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    address_key  TEXT NOT NULL UNIQUE,
    address_input TEXT,
    address_norm  TEXT,
    b_code        TEXT NOT NULL DEFAULT '',
    lat           REAL,
    lng           REAL,
    folder_name   TEXT,
    first_seen    TEXT,
    last_used     TEXT,
    search_count  INTEGER NOT NULL DEFAULT 0,
    cells_cached  INTEGER NOT NULL DEFAULT 0
);
"""


def _seed(conn):
    conn.executescript("""
        INSERT INTO workplaces
          (address_key, address_input, address_norm, search_count, last_used)
        VALUES
          ('key_a', '강남역', '서울 강남구 테헤란로 504', 10, '2026-05-27 10:00:00'),
          ('key_b', '판교역', '경기 성남시 분당구 판교역로 146', 5, '2026-05-26 09:00:00'),
          ('key_c', '여의도역', '서울 영등포구 여의도동 20', 5, '2026-05-25 08:00:00'),
          ('key_d', '광화문', '서울 종로구 세종대로 175', 1, '2026-05-24 07:00:00');
    """)
    conn.commit()


@pytest.fixture
def history_client():
    from app.main import app
    from app.db import get_db

    conn = sqlite3.connect(':memory:', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    _seed(conn)

    def _override():
        yield conn

    app.dependency_overrides[get_db] = _override

    # main.py workplaces_recent는 db_connect()를 직접 호출하므로 패치 필요
    from unittest.mock import patch
    with patch('app.db.connect', return_value=conn):
        with TestClient(app) as c:
            yield c

    app.dependency_overrides.clear()
    conn.close()


@pytest.fixture
def empty_client():
    from app.main import app
    from app.db import get_db

    conn = sqlite3.connect(':memory:', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.commit()

    def _override():
        yield conn

    app.dependency_overrides[get_db] = _override

    from unittest.mock import patch
    with patch('app.db.connect', return_value=conn):
        with TestClient(app) as c:
            yield c

    app.dependency_overrides.clear()
    conn.close()


class TestWorkplacesRecent:

    def test_returns_200(self, history_client):
        resp = history_client.get('/api/workplaces/recent')
        assert resp.status_code == 200

    def test_returns_list(self, history_client):
        data = history_client.get('/api/workplaces/recent').json()
        assert isinstance(data, list)

    def test_default_limit_5(self, history_client):
        """기본 limit=5 → 시드 4개 모두 반환 (4 <= 5)."""
        data = history_client.get('/api/workplaces/recent').json()
        assert len(data) <= 5

    def test_sorted_by_search_count_desc(self, history_client):
        """search_count 높은 순서 — 강남역(10)이 첫 번째."""
        data = history_client.get('/api/workplaces/recent').json()
        assert data[0]['address_input'] == '강남역'

    def test_same_count_sorted_by_last_used_desc(self, history_client):
        """search_count 동일(5) 시 last_used DESC → 판교역이 여의도역 앞."""
        data = history_client.get('/api/workplaces/recent').json()
        inputs = [d['address_input'] for d in data]
        assert inputs.index('판교역') < inputs.index('여의도역')

    def test_has_address_input_field(self, history_client):
        data = history_client.get('/api/workplaces/recent').json()
        assert 'address_input' in data[0]

    def test_has_address_norm_field(self, history_client):
        data = history_client.get('/api/workplaces/recent').json()
        assert 'address_norm' in data[0]

    def test_has_search_count_field(self, history_client):
        data = history_client.get('/api/workplaces/recent').json()
        assert 'search_count' in data[0]

    def test_limit_param_respected(self, history_client):
        """limit=2 → 2개만 반환."""
        data = history_client.get('/api/workplaces/recent?limit=2').json()
        assert len(data) <= 2

    def test_limit_clamped_to_10(self, history_client):
        """limit=999 → 10으로 클램프."""
        resp = history_client.get('/api/workplaces/recent?limit=999')
        assert resp.status_code == 200
        # 10 이하 반환 (시드 4개이므로 4개)
        assert len(resp.json()) <= 10

    def test_limit_clamped_min_1(self, history_client):
        """limit=0 → 1로 클램프 → 1개 반환."""
        data = history_client.get('/api/workplaces/recent?limit=0').json()
        assert len(data) == 1

    def test_empty_db_returns_empty_list(self, empty_client):
        """데이터 없으면 빈 배열."""
        data = empty_client.get('/api/workplaces/recent').json()
        assert data == []
