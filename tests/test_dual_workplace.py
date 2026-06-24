"""
tests/test_dual_workplace.py — spec-13 Dual Workplace 테스트

검증 범위:
  1. Pydantic 유효성 검사  — 동일 주소 422, W2 주소 실패 400
  2. Dual 파이프라인       — 200 응답, dual 필드, meta.dual_workplace
  3. 교집합 없음           — W2 위치가 멀어 반경 교집합 매물 0개
  4. 단일 모드 하위 호환   — workplace_address_2 없으면 total_time_min_2=None
"""
import sqlite3
import pytest
from unittest.mock import patch

from tests.test_search_pipeline import _FULL_SCHEMA, _seed_db

# ── 테스트 픽스처용 더미 직장 ──────────────────────────────────
_FAKE_WP_1 = {
    'wp_id': 1,
    'lat': 37.4979, 'lng': 127.0276,
    'address_norm': '서울 강남구 테헤란로 504',
    'address_input': '강남역',
    'folder_name': 'test_wp',
    'b_code': '1168010100',
}

# W2: APT001(37.495, 127.025)과 ~0.5km → 반경 교집합 포함
_FAKE_WP_2 = {
    'wp_id': 2,
    'lat': 37.4920, 'lng': 127.0210,
    'address_norm': '서울 강남구 역삼로 152',
    'address_input': '역삼역',
    'folder_name': 'test_wp2',
    'b_code': '1168010200',
}

# W2 far: 부산 → APT001과 반경 교집합 없음
_FAKE_WP_2_FAR = {
    'wp_id': 2,
    'lat': 35.1028, 'lng': 129.0244,
    'address_norm': '부산 부산진구 중앙대로 672',
    'address_input': '부산역',
    'folder_name': 'test_wp2_far',
    'b_code': '2614010100',
}


def _seed_db_dual(conn):
    """기본 시드 + W2 직장·경로 데이터 추가."""
    _seed_db(conn)  # wp_id=1, APT001, transit_cache/routes wp_id=1

    # W2 직장
    conn.execute(
        "INSERT INTO workplaces "
        "(wp_id, address_key, address_input, address_norm, b_code, lat, lng, folder_name) "
        "VALUES (2, 'key_yeoksam', '역삼역', '서울 강남구 역삼로 152',"
        " '1168010200', 37.4920, 127.0210, 'test_wp2')"
    )
    # W2 transit_cache: passed_filter=1 → ODsay 호출 없음
    conn.execute(
        "INSERT INTO transit_cache (origin_cell, wp_id, passed_filter, total_time) "
        "VALUES ('R08333C28422', 2, 1, 32)"
    )
    # W2 transit_routes: 32분
    conn.execute(
        "INSERT INTO transit_routes "
        "(origin_cell, wp_id, rank, total_time_min, bus_cnt, subway_cnt) "
        "VALUES ('R08333C28422', 2, 1, 32, 1, 0)"
    )
    conn.commit()


@pytest.fixture
def dual_db():
    conn = sqlite3.connect(':memory:', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_FULL_SCHEMA)
    _seed_db_dual(conn)
    yield conn
    conn.close()


@pytest.fixture
def dual_client(dual_db):
    from app.main import app
    from app.db import get_db

    def _override():
        yield dual_db

    app.dependency_overrides[get_db] = _override
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── 유효성 검사 ───────────────────────────────────────────────

class TestDualValidation:

    def test_same_address_returns_422(self, dual_client):
        """W1 == W2 (정규화 전 동일 문자열) → Pydantic validator 422."""
        resp = dual_client.post('/api/search', json={
            'workplace_address': '강남역',
            'workplace_address_2': '강남역',
        })
        assert resp.status_code == 422

    def test_same_address_stripped_returns_422(self, dual_client):
        """공백 포함 동일 주소도 422."""
        resp = dual_client.post('/api/search', json={
            'workplace_address': '강남역',
            'workplace_address_2': ' 강남역 ',
        })
        assert resp.status_code == 422

    def test_wp2_conversion_failure_returns_400(self, dual_client):
        """W2 주소 변환 실패(None) → 400."""
        def side(conn, addr, **kw):
            if addr == '강남역':
                return _FAKE_WP_1
            return None  # W2 실패

        with patch('app.search.get_or_create', side_effect=side):
            resp = dual_client.post('/api/search', json={
                'workplace_address': '강남역',
                'workplace_address_2': '없는주소',
            })
        assert resp.status_code == 400

    def test_wp2_same_wp_id_returns_422(self, dual_client):
        """W1·W2가 주소 다르지만 같은 wp_id 반환 → 422."""
        with (
            patch('app.search.get_or_create', return_value=_FAKE_WP_1),        ):
            resp = dual_client.post('/api/search', json={
                'workplace_address': '강남역',
                'workplace_address_2': '다른주소지만같은ID',
            })
        assert resp.status_code == 422


# ── Dual 파이프라인 정상 케이스 ──────────────────────────────

class TestDualPipeline:

    def _post(self, client, extra=None):
        payload = {
            'workplace_address': '강남역',
            'workplace_address_2': '역삼역',
            'max_minutes': 60,
            'max_price': 50000,
            'pyeong_types': ['20평대'],
        }
        if extra:
            payload.update(extra)

        call_count = {'n': 0}

        def side(conn, addr, **kw):
            call_count['n'] += 1
            return _FAKE_WP_1 if call_count['n'] == 1 else _FAKE_WP_2

        # DATABASE_URL 환경변수가 있으면 USE_PG=True → SQLite에서 GREATEST() 실패
        # 테스트는 in-memory SQLite 사용이므로 USE_PG=False 강제
        with (
            patch('app.portable.USE_PG', False),
            patch('app.search.get_or_create', side_effect=side),        ):
            return client.post('/api/search', json=payload)

    def test_returns_200(self, dual_client):
        assert self._post(dual_client).status_code == 200

    def test_has_cards(self, dual_client):
        data = self._post(dual_client).json()
        assert len(data['cards']) >= 1

    def test_meta_dual_workplace_true(self, dual_client):
        data = self._post(dual_client).json()
        assert data['meta']['dual_workplace'] is True

    def test_workplace_2_field_present(self, dual_client):
        data = self._post(dual_client).json()
        assert 'workplace_2' in data
        assert data['workplace_2'] is not None

    def test_workplace_2_address_norm(self, dual_client):
        data = self._post(dual_client).json()
        assert data['workplace_2']['address_norm'] == '서울 강남구 역삼로 152'

    def test_card_has_total_time_min_1(self, dual_client):
        data = self._post(dual_client).json()
        assert 'total_time_min_1' in data['cards'][0]

    def test_card_has_total_time_min_2(self, dual_client):
        data = self._post(dual_client).json()
        assert 'total_time_min_2' in data['cards'][0]

    def test_card_total_time_min_1_value(self, dual_client):
        """시드: W1 경로 25분."""
        data = self._post(dual_client).json()
        assert data['cards'][0]['total_time_min_1'] == 25

    def test_card_total_time_min_2_value(self, dual_client):
        """시드: W2 경로 32분."""
        data = self._post(dual_client).json()
        assert data['cards'][0]['total_time_min_2'] == 32

    def test_card_total_time_min_is_max(self, dual_client):
        """total_time_min = max(t1, t2) = 32."""
        data = self._post(dual_client).json()
        c = data['cards'][0]
        assert c['total_time_min'] == max(c['total_time_min_1'], c['total_time_min_2'])

    def test_meta_odsay_calls_zero(self, dual_client):
        """transit_cache passed_filter=1 → ODsay 호출 없음."""
        data = self._post(dual_client).json()
        # dual 모드: odsay_calls_made_1 + odsay_calls_made_2 모두 0
        assert data['meta'].get('odsay_calls_made_1', 0) == 0
        assert data['meta'].get('odsay_calls_made_2', 0) == 0


# ── 교집합 없음 케이스 ──────────────────────────────────────

class TestDualNoIntersection:

    def test_empty_cards_when_no_intersection(self, dual_client):
        """W2 위치가 부산 → APT001이 W2 반경 밖 → 교집합 0."""
        call_count = {'n': 0}

        def side(conn, addr, **kw):
            call_count['n'] += 1
            return _FAKE_WP_1 if call_count['n'] == 1 else _FAKE_WP_2_FAR

        with (
            patch('app.search.get_or_create', side_effect=side),        ):
            resp = dual_client.post('/api/search', json={
                'workplace_address': '강남역',
                'workplace_address_2': '부산역',
                'max_minutes': 60,
            })

        assert resp.status_code == 200
        assert resp.json()['cards'] == []

    def test_meta_dual_true_even_when_empty(self, dual_client):
        """교집합 없어도 dual_workplace=True 유지."""
        call_count = {'n': 0}

        def side(conn, addr, **kw):
            call_count['n'] += 1
            return _FAKE_WP_1 if call_count['n'] == 1 else _FAKE_WP_2_FAR

        with (
            patch('app.search.get_or_create', side_effect=side),        ):
            data = dual_client.post('/api/search', json={
                'workplace_address': '강남역',
                'workplace_address_2': '부산역',
                'max_minutes': 60,
            }).json()

        assert data['meta']['dual_workplace'] is True


# ── 단일 모드 하위 호환 ──────────────────────────────────────

class TestSingleModeBackcompat:

    def _post(self, client):
        with (
            patch('app.search.get_or_create', return_value=_FAKE_WP_1),        ):
            return client.post('/api/search', json={
                'workplace_address': '강남역',
                'max_minutes': 60,
                'max_price': 50000,
                'pyeong_types': ['20평대'],
            })

    def test_meta_dual_false_when_single(self, dual_client):
        data = self._post(dual_client).json()
        assert data['meta']['dual_workplace'] is False

    def test_workplace_2_null_when_single(self, dual_client):
        data = self._post(dual_client).json()
        assert data.get('workplace_2') is None

    def test_card_total_time_min_2_none_when_single(self, dual_client):
        """단일 모드: total_time_min_2 = None."""
        data = self._post(dual_client).json()
        assert data['cards'][0]['total_time_min_2'] is None
