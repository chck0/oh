"""
tests/test_price_change_badge.py — spec-16 가격 변동률 배지

검증 범위:
  1. price_chg_6m_pct 필드 존재 (카드 응답에 포함)
  2. 상승 케이스: 최근 3개월 평균 > 이전 6개월 평균, |변동| >= 3% → 양수 반환
  3. 하락 케이스: 최근 3개월 평균 < 이전 6개월 평균, |변동| >= 3% → 음수 반환
  4. 미달 케이스: |변동률| < 3% → None 반환
  5. 거래 데이터 없음 → None (graceful degradation)
  6. trade_history 없어도 500 없음
"""
import sqlite3
import datetime
import pytest
from unittest.mock import patch


# ── Full schema (test_search_pipeline.py 와 동일 베이스) ─────────────────────
_FULL_SCHEMA = """
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
CREATE TABLE IF NOT EXISTS apartments (
    apt_seq      TEXT,
    apt_nm       TEXT,
    sgg_cd       TEXT,
    umd_nm       TEXT,
    lat          REAL,
    lng          REAL,
    grid_key     TEXT,
    kaptCode     TEXT,
    kaptdaCnt    REAL,
    recent_trade INTEGER,
    is_apt       INTEGER NOT NULL DEFAULT 0,
    build_year   INTEGER
);
CREATE TABLE IF NOT EXISTS kapt_complexes (
    kaptCode     TEXT PRIMARY KEY,
    kaptTopFloor INTEGER,
    kaptUsedate  TEXT
);
CREATE TABLE IF NOT EXISTS trade_recent (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    apt_seq         TEXT,
    pyeong_type     TEXT,
    pyeong          REAL,
    floor           INTEGER,
    deal_amount_int INTEGER,
    deal_year       INTEGER,
    deal_month      INTEGER,
    deal_day        INTEGER,
    dealing_gbn     TEXT
);
CREATE TABLE IF NOT EXISTS trade_history (
    apt_seq         TEXT,
    deal_year       INTEGER,
    deal_month      INTEGER,
    deal_price      INTEGER,
    pyeong_type     TEXT,
    deal_amount_int INTEGER
);
CREATE TABLE IF NOT EXISTS transit_cache (
    origin_cell   TEXT,
    wp_id         INTEGER,
    total_time    INTEGER,
    bus_cnt       INTEGER,
    subway_cnt    INTEGER,
    walk_total    INTEGER,
    passed_filter INTEGER,
    path_idx      INTEGER,
    raw_file      TEXT,
    response_size INTEGER,
    fetched_at    TEXT,
    PRIMARY KEY (origin_cell, wp_id)
);
CREATE TABLE IF NOT EXISTS transit_routes (
    origin_cell     TEXT,
    wp_id           INTEGER,
    rank            INTEGER,
    total_time_min  INTEGER,
    bus_cnt         INTEGER,
    subway_cnt      INTEGER,
    step1_type TEXT, step1_time_min INTEGER, step1_dist_m INTEGER,
    "step1_노선" TEXT, "step1_출발" TEXT, "step1_도착" TEXT,
    step2_type TEXT, step2_time_min INTEGER, step2_dist_m INTEGER,
    "step2_노선" TEXT, "step2_출발" TEXT, "step2_도착" TEXT,
    step3_type TEXT, step3_time_min INTEGER, step3_dist_m INTEGER,
    "step3_노선" TEXT, "step3_출발" TEXT, "step3_도착" TEXT,
    step4_type TEXT, step4_time_min INTEGER, step4_dist_m INTEGER,
    "step4_노선" TEXT, "step4_출발" TEXT, "step4_도착" TEXT,
    step5_type TEXT, step5_time_min INTEGER, step5_dist_m INTEGER,
    "step5_노선" TEXT, "step5_출발" TEXT, "step5_도착" TEXT
);
CREATE TABLE IF NOT EXISTS apt_pt_friend_comment (
    apt_seq    TEXT,
    pyeong_type TEXT,
    wp_id      INTEGER,
    comment    TEXT,
    model      TEXT,
    created_at TEXT,
    PRIMARY KEY (apt_seq, pyeong_type, wp_id)
);
CREATE TABLE IF NOT EXISTS trade_tags (
    apt_seq     TEXT,
    pyeong_type TEXT,
    tag_type    TEXT,
    label       TEXT,
    detail      TEXT,
    calc_date   TEXT,
    PRIMARY KEY (apt_seq, pyeong_type, tag_type)
);
"""

_FAKE_WP = {
    'wp_id': 1,
    'lat': 37.4979, 'lng': 127.0276,
    'address_norm': '서울 강남구 테헤란로 504',
    'address_input': '강남역',
    'folder_name': 'test_wp',
    'b_code': '1168010100',
}


def _today_ym_offset(months_back: int) -> tuple[int, int]:
    """(year, month) months_back 개월 전."""
    today = datetime.date.today()
    y, m = today.year, today.month - months_back
    while m <= 0:
        m += 12
        y -= 1
    return y, m


def _seed_base(conn):
    """공통 기반 시드: workplace, apartment, transit_cache, transit_routes."""
    conn.execute(
        "INSERT INTO workplaces (wp_id, address_key, address_input, address_norm, "
        "b_code, lat, lng) VALUES (1,'k1','강남역','서울 강남구 테헤란로 504','1168010100',37.4979,127.0276)"
    )
    conn.execute(
        "INSERT INTO apartments (apt_seq, apt_nm, umd_nm, lat, lng, grid_key, "
        "kaptCode, kaptdaCnt, is_apt) VALUES "
        "('APT001','테스트아파트','역삼동',37.50,127.03,'CELL01','KAPT01',500,1)"
    )
    conn.execute(
        "INSERT INTO kapt_complexes (kaptCode, kaptTopFloor, kaptUsedate) "
        "VALUES ('KAPT01', 20, '20100101')"
    )
    conn.execute(
        "INSERT INTO transit_cache (origin_cell, wp_id, passed_filter) "
        "VALUES ('CELL01', 1, 1)"
    )
    conn.execute(
        "INSERT INTO transit_routes (origin_cell, wp_id, rank, total_time_min, "
        "bus_cnt, subway_cnt) VALUES ('CELL01', 1, 1, 25, 1, 1)"
    )
    conn.execute(
        "INSERT INTO trade_recent (apt_seq, pyeong_type, pyeong, floor, "
        "deal_amount_int, deal_year, deal_month, deal_day, dealing_gbn) "
        "VALUES ('APT001', '30평대', 32.5, 10, 80000, 2026, 4, 15, '중개거래')"
    )
    conn.commit()


def _seed_price_up(conn):
    """상승 케이스: 최근 3개월 평균 > 이전 6개월 평균, 변동 +10%."""
    r_y, r_m = _today_ym_offset(1)   # 1개월 전 (최근 구간 안)
    p_y, p_m = _today_ym_offset(6)   # 6개월 전 (과거 구간 안)
    conn.execute(
        "INSERT INTO trade_history (apt_seq, pyeong_type, deal_year, deal_month, deal_amount_int) "
        f"VALUES ('APT001', '30평대', {r_y}, {r_m}, 88000)"   # 최근: 8.8억
    )
    conn.execute(
        "INSERT INTO trade_history (apt_seq, pyeong_type, deal_year, deal_month, deal_amount_int) "
        f"VALUES ('APT001', '30평대', {p_y}, {p_m}, 80000)"   # 과거: 8.0억
    )
    conn.commit()


def _seed_price_down(conn):
    """하락 케이스: 최근 3개월 평균 < 이전 6개월 평균, 변동 -10%."""
    r_y, r_m = _today_ym_offset(1)
    p_y, p_m = _today_ym_offset(6)
    conn.execute(
        "INSERT INTO trade_history (apt_seq, pyeong_type, deal_year, deal_month, deal_amount_int) "
        f"VALUES ('APT001', '30평대', {r_y}, {r_m}, 72000)"   # 최근: 7.2억
    )
    conn.execute(
        "INSERT INTO trade_history (apt_seq, pyeong_type, deal_year, deal_month, deal_amount_int) "
        f"VALUES ('APT001', '30평대', {p_y}, {p_m}, 80000)"   # 과거: 8.0억
    )
    conn.commit()


def _seed_price_flat(conn):
    """노이즈 케이스: 변동률 1% (3% 미달 → None)."""
    r_y, r_m = _today_ym_offset(1)
    p_y, p_m = _today_ym_offset(6)
    conn.execute(
        "INSERT INTO trade_history (apt_seq, pyeong_type, deal_year, deal_month, deal_amount_int) "
        f"VALUES ('APT001', '30평대', {r_y}, {r_m}, 80800)"   # +1%
    )
    conn.execute(
        "INSERT INTO trade_history (apt_seq, pyeong_type, deal_year, deal_month, deal_amount_int) "
        f"VALUES ('APT001', '30평대', {p_y}, {p_m}, 80000)"
    )
    conn.commit()


def _make_client(conn):
    """TestClient — get_db 의존성 오버라이드."""
    from app.main import app
    from app.db import get_db
    from fastapi.testclient import TestClient

    def _override():
        yield conn

    app.dependency_overrides[get_db] = _override
    return TestClient(app)


def _post_search(client):
    from unittest.mock import patch as mpatch
    with (
        mpatch('app.search.get_or_create', return_value=_FAKE_WP),
        mpatch('app.portable.USE_PG', False),
    ):
        return client.post('/api/search', json={
            'workplace_address': '강남역',
            'max_minutes': 60,
            'max_price': 200000,
            'pyeong_types': ['30평대'],
        })


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _fixture_client(seed_fn=None):
    """fixture 공통 패턴 — conn 생성 → 시드 → TestClient."""
    conn = sqlite3.connect(':memory:', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_FULL_SCHEMA)
    _seed_base(conn)
    if seed_fn:
        seed_fn(conn)
    client = _make_client(conn)
    return conn, client


@pytest.fixture
def up_client():
    conn, client = _fixture_client(_seed_price_up)
    yield client
    from app.main import app
    app.dependency_overrides.clear()
    conn.close()


@pytest.fixture
def down_client():
    conn, client = _fixture_client(_seed_price_down)
    yield client
    from app.main import app
    app.dependency_overrides.clear()
    conn.close()


@pytest.fixture
def flat_client():
    conn, client = _fixture_client(_seed_price_flat)
    yield client
    from app.main import app
    app.dependency_overrides.clear()
    conn.close()


@pytest.fixture
def no_history_client():
    """trade_history 데이터 없는 케이스."""
    conn, client = _fixture_client()   # seed_fn 없음 = trade_history 비어 있음
    yield client
    from app.main import app
    app.dependency_overrides.clear()
    conn.close()


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestPriceChangeBadgeField:

    def test_field_exists_in_card(self, no_history_client):
        """price_chg_6m_pct 필드가 카드 응답에 존재해야 한다."""
        resp = _post_search(no_history_client)
        assert resp.status_code == 200
        data = resp.json()
        cards = data.get('cards', [])
        if cards:
            assert 'price_chg_6m_pct' in cards[0], "price_chg_6m_pct 필드 누락"

    def test_no_history_returns_none(self, no_history_client):
        """거래 데이터 없으면 price_chg_6m_pct = None."""
        data = _post_search(no_history_client).json()
        for card in data.get('cards', []):
            assert card['price_chg_6m_pct'] is None

    def test_no_500_without_history(self, no_history_client):
        """trade_history 데이터 없어도 500 없음 (graceful degradation)."""
        resp = _post_search(no_history_client)
        assert resp.status_code == 200


class TestPriceChangeUp:

    def test_up_returns_positive(self, up_client):
        """상승 케이스: price_chg_6m_pct > 0."""
        data = _post_search(up_client).json()
        cards = [c for c in data.get('cards', [])
                 if c.get('apt_seq') == 'APT001' and c.get('pyeong_type') == '30평대']
        if cards:
            pct = cards[0]['price_chg_6m_pct']
            assert pct is not None and pct > 0, f"상승 케이스인데 pct={pct}"

    def test_up_above_threshold(self, up_client):
        """상승 케이스: 변동률 >= 3%."""
        data = _post_search(up_client).json()
        cards = [c for c in data.get('cards', [])
                 if c.get('apt_seq') == 'APT001' and c.get('pyeong_type') == '30평대']
        if cards and cards[0]['price_chg_6m_pct'] is not None:
            assert abs(cards[0]['price_chg_6m_pct']) >= 3.0


class TestPriceChangeDown:

    def test_down_returns_negative(self, down_client):
        """하락 케이스: price_chg_6m_pct < 0."""
        data = _post_search(down_client).json()
        cards = [c for c in data.get('cards', [])
                 if c.get('apt_seq') == 'APT001' and c.get('pyeong_type') == '30평대']
        if cards:
            pct = cards[0]['price_chg_6m_pct']
            assert pct is not None and pct < 0, f"하락 케이스인데 pct={pct}"

    def test_down_above_threshold(self, down_client):
        """하락 케이스: |변동률| >= 3%."""
        data = _post_search(down_client).json()
        cards = [c for c in data.get('cards', [])
                 if c.get('apt_seq') == 'APT001' and c.get('pyeong_type') == '30평대']
        if cards and cards[0]['price_chg_6m_pct'] is not None:
            assert abs(cards[0]['price_chg_6m_pct']) >= 3.0


class TestPriceChangeFlat:

    def test_flat_returns_none(self, flat_client):
        """|변동률| < 3% → None 반환 (노이즈 제거)."""
        data = _post_search(flat_client).json()
        for card in data.get('cards', []):
            if card.get('apt_seq') == 'APT001':
                assert card['price_chg_6m_pct'] is None, (
                    f"1% 변동인데 None이 아님: {card['price_chg_6m_pct']}"
                )
