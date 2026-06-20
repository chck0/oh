"""
app/search.py 통합 테스트

POST /api/search 파이프라인 검증:
- 잘못된 입력 → 400/422
- 반경 내 단지 없음 → 빈 cards + 기본 구조 반환
- 정상 파이프라인 → 200, 응답 구조 + 카드 내용 검증

conftest.py 의 _SCHEMA 는 trade_recent 가 집계 컬럼(price_low, deal_count …) 형태라
카드 쿼리(개별 거래행 기반)와 맞지 않으므로 이 파일 전용 _FULL_SCHEMA 를 사용한다.
"""
import sqlite3
import pytest
from unittest.mock import patch


# ── 검색 전용 스키마 ───────────────────────────────────────────
# trade_recent: 개별 거래행 (id PK, deal_amount_int, deal_year/month/day …)
# apt_pt_friend_comment: (apt_seq, pyeong_type, wp_id) PK
_FULL_SCHEMA = """
CREATE TABLE IF NOT EXISTS workplaces (
    wp_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    address_key  TEXT NOT NULL UNIQUE,
    address_input TEXT,
    address_norm  TEXT,
    b_code        TEXT NOT NULL DEFAULT '',
    main_bun      TEXT,
    sub_bun       TEXT,
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
    origin_cell    TEXT,
    wp_id          INTEGER,
    rank           INTEGER,
    total_time_min INTEGER,
    bus_cnt        INTEGER,
    subway_cnt     INTEGER,
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
    apt_seq     TEXT,
    pyeong_type TEXT,
    wp_id       INTEGER,
    comment     TEXT,
    kind        TEXT,
    created_at  TEXT,
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

CREATE TABLE IF NOT EXISTS apt_walking_poi (
    kaptCode     TEXT,
    poi_lclas_cd TEXT,
    poi_mlsfc_cd TEXT,
    poi_nm       TEXT,
    distance_m   REAL,
    walking_min  INTEGER
);
"""

# wp_id=1 직장 — Kakao 호출 없이 바로 반환할 딕셔너리
_FAKE_WP = {
    'wp_id': 1,
    'lat': 37.4979,
    'lng': 127.0276,
    'address_norm': '서울 강남구 테헤란로 504',
    'address_input': '강남역',
    'folder_name': 'test_wp',
    'b_code': '1168010100',
}


def _seed_db(conn):
    """검색 파이프라인 최소 데이터 삽입."""
    # 직장
    conn.execute(
        "INSERT INTO workplaces "
        "(wp_id, address_key, address_input, address_norm, b_code, lat, lng, folder_name) "
        "VALUES (1, 'key_gangnam', '강남역', '서울 강남구 테헤란로 504',"
        " '1168010100', 37.4979, 127.0276, 'test_wp')"
    )
    # 직장과 가까운 아파트 (haversine ~0.5km → 반경 15km 이내)
    conn.execute(
        "INSERT INTO apartments "
        "(apt_seq, apt_nm, umd_nm, lat, lng, grid_key, kaptCode, kaptdaCnt, recent_trade, is_apt) "
        "VALUES ('APT001', '테스트아파트', '역삼동', 37.495, 127.025,"
        " 'R08333C28422', 'K001', 500.0, 3, 1)"
    )
    # transit_cache: passed_filter=1 → to_fetch=[] → ODsay 호출 0건
    conn.execute(
        "INSERT INTO transit_cache (origin_cell, wp_id, passed_filter, total_time) "
        "VALUES ('R08333C28422', 1, 1, 25)"
    )
    # transit_routes: rank=1, 25분, 지하철 1회
    conn.execute(
        "INSERT INTO transit_routes "
        "(origin_cell, wp_id, rank, total_time_min, bus_cnt, subway_cnt) "
        "VALUES ('R08333C28422', 1, 1, 25, 0, 1)"
    )
    # trade_recent: 2026년 4월 거래 (threshold=year_month_minus(3)=202602 통과)
    conn.execute(
        "INSERT INTO trade_recent "
        "(apt_seq, pyeong_type, pyeong, floor, deal_amount_int, deal_year, deal_month, deal_day, dealing_gbn) "
        "VALUES ('APT001', '20평대', 27.5, 10, 30000, 2026, 4, 15, '중개거래')"
    )
    # trade_tags: 1층 태그 사전 삽입
    conn.execute(
        "INSERT INTO trade_tags (apt_seq, pyeong_type, tag_type, label, detail) "
        "VALUES ('APT001', '20평대', 'floor', '1층 매물', NULL)"
    )
    conn.commit()


@pytest.fixture
def full_db():
    """검색 파이프라인 전용 in-memory SQLite DB.

    check_same_thread=False: FastAPI async 핸들러는 이벤트 루프 전용 스레드에서
    실행되므로, 테스트 스레드에서 만든 연결을 그대로 전달하려면 이 플래그가 필요.
    """
    conn = sqlite3.connect(':memory:', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_FULL_SCHEMA)
    _seed_db(conn)
    yield conn
    conn.close()


@pytest.fixture
def full_client(full_db):
    """FastAPI TestClient — get_db 의존성을 full_db 로 교체."""
    from app.main import app
    from app.db import get_db

    def _override():
        yield full_db

    app.dependency_overrides[get_db] = _override
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── 오류 케이스 ────────────────────────────────────────────────

class TestSearchEndpointErrors:
    """잘못된 입력 / 주소 실패 / 반경 밖 케이스."""

    def test_address_conversion_failure_returns_400(self, full_client):
        """get_or_create → None 이면 400 반환."""
        with patch('app.search.get_or_create', return_value=None):
            resp = full_client.post('/api/search', json={'workplace_address': '없는주소'})
        assert resp.status_code == 400

    def test_invalid_pyeong_type_returns_422(self, full_client):
        """허용되지 않는 평형값은 Pydantic validator 에서 422."""
        resp = full_client.post('/api/search', json={
            'workplace_address': '강남역',
            'pyeong_types': ['잘못된평형'],
        })
        assert resp.status_code == 422

    def test_address_too_short_returns_422(self, full_client):
        """주소 min_length=2 미만 → 422."""
        resp = full_client.post('/api/search', json={'workplace_address': 'X'})
        assert resp.status_code == 422

    def test_max_minutes_below_min_returns_422(self, full_client):
        """max_minutes ge=10 미만 → 422."""
        resp = full_client.post('/api/search', json={
            'workplace_address': '강남역',
            'max_minutes': 5,
        })
        assert resp.status_code == 422

    def test_build_year_min_too_low_returns_422(self, full_client):
        """build_year_min ge=1960 미만 → 422. (AC3)"""
        resp = full_client.post('/api/search', json={
            'workplace_address': '강남역',
            'build_year_min': 1900,
        })
        assert resp.status_code == 422

    def test_build_year_min_too_high_returns_422(self, full_client):
        """build_year_min le=2030 초과 → 422."""
        resp = full_client.post('/api/search', json={
            'workplace_address': '강남역',
            'build_year_min': 2099,
        })
        assert resp.status_code == 422

    def test_no_near_apts_returns_200(self, full_client):
        """반경 밖 직장 → 빈 응답이지만 200."""
        far_wp = dict(_FAKE_WP, lat=35.0, lng=129.0)
        with patch('app.search.get_or_create', return_value=far_wp):
            resp = full_client.post('/api/search', json={'workplace_address': '부산역'})
        assert resp.status_code == 200

    def test_no_near_apts_returns_empty_cards(self, full_client):
        far_wp = dict(_FAKE_WP, lat=35.0, lng=129.0)
        with patch('app.search.get_or_create', return_value=far_wp):
            data = full_client.post('/api/search', json={'workplace_address': '부산역'}).json()
        assert data['cards'] == []

    def test_no_near_apts_has_stats_and_buckets(self, full_client):
        far_wp = dict(_FAKE_WP, lat=35.0, lng=129.0)
        with patch('app.search.get_or_create', return_value=far_wp):
            data = full_client.post('/api/search', json={'workplace_address': '부산역'}).json()
        assert 'stats' in data
        assert 'buckets' in data


# ── 정상 케이스 ────────────────────────────────────────────────

class TestSearchEndpointSuccess:
    """시드 데이터(transit_cache passed_filter=1)로 카드 1장 반환 검증."""

    def _post(self, client, extra=None):
        payload = {
            'workplace_address': '강남역',
            'max_minutes': 60,
            'max_price': 50000,
            'pyeong_types': ['20평대'],
        }
        if extra:
            payload.update(extra)
        with (
            patch('app.search.get_or_create', return_value=_FAKE_WP),
        ):
            return client.post('/api/search', json=payload)

    def test_returns_200(self, full_client):
        assert self._post(full_client).status_code == 200

    def test_has_cards_field(self, full_client):
        assert 'cards' in self._post(full_client).json()

    def test_has_stats_field(self, full_client):
        assert 'stats' in self._post(full_client).json()

    def test_has_buckets_field(self, full_client):
        assert 'buckets' in self._post(full_client).json()

    def test_has_workplace_field(self, full_client):
        assert 'workplace' in self._post(full_client).json()

    def test_has_meta_field(self, full_client):
        assert 'meta' in self._post(full_client).json()

    def test_cards_not_empty(self, full_client):
        data = self._post(full_client).json()
        assert len(data['cards']) >= 1

    def test_card_apt_nm(self, full_client):
        data = self._post(full_client).json()
        assert data['cards'][0]['apt_nm'] == '테스트아파트'

    def test_card_total_time_min(self, full_client):
        data = self._post(full_client).json()
        assert data['cards'][0]['total_time_min'] == 25

    def test_card_pyeong_type(self, full_client):
        data = self._post(full_client).json()
        assert data['cards'][0]['pyeong_type'] == '20평대'

    def test_meta_odsay_calls_zero(self, full_client):
        """transit_cache passed_filter=1 → to_fetch=[] → ODsay 호출 없음."""
        data = self._post(full_client).json()
        assert data['meta']['odsay_calls_made'] == 0

    def test_meta_cache_hits_gte_one(self, full_client):
        data = self._post(full_client).json()
        assert data['meta']['cache_hits'] >= 1

    def test_wp_id_in_response(self, full_client):
        data = self._post(full_client).json()
        assert data['wp_id'] == 1

    def test_workplace_address_norm(self, full_client):
        data = self._post(full_client).json()
        assert data['workplace']['address_norm'] == '서울 강남구 테헤란로 504'

    def test_card_has_why_tags_field(self, full_client):
        data = self._post(full_client).json()
        assert 'why_tags' in data['cards'][0]

    def test_why_tags_is_list(self, full_client):
        data = self._post(full_client).json()
        assert isinstance(data['cards'][0]['why_tags'], list)

    def test_why_tags_has_seeded_label(self, full_client):
        """_seed_db 에 삽입한 '1층 매물' 태그가 카드에 포함돼야 함."""
        data = self._post(full_client).json()
        labels = [t['label'] for t in data['cards'][0]['why_tags']]
        assert '1층 매물' in labels


# ── 준공연도 필터 케이스 ────────────────────────────────────────

class TestSearchBuildYearFilter:
    """build_year_min 파라미터 필터링 검증 (spec-07)."""

    def _post(self, client, extra=None):
        payload = {
            'workplace_address': '강남역',
            'max_minutes': 60,
            'max_price': 50000,
            'pyeong_types': ['20평대'],
        }
        if extra:
            payload.update(extra)
        with (
            patch('app.search.get_or_create', return_value=_FAKE_WP),
        ):
            return client.post('/api/search', json=payload)

    def test_null_build_year_excluded_when_filter_set(self, full_client):
        """시드 아파트는 build_year=NULL → build_year_min 지정 시 cards 빈 배열. (AC4)"""
        data = self._post(full_client, {'build_year_min': 2015}).json()
        assert data['cards'] == []

    def test_no_filter_returns_card(self, full_client):
        """build_year_min 미지정 → 기존대로 카드 반환. (AC2 회귀 없음)"""
        data = self._post(full_client).json()
        assert len(data['cards']) >= 1

    def test_build_year_min_1960_with_matching_apt(self, full_client, full_db):
        """build_year=1980 단지 삽입 후 build_year_min=1960 → 포함됨. (AC1)"""
        full_db.execute(
            "INSERT INTO apartments "
            "(apt_seq, apt_nm, umd_nm, lat, lng, grid_key, kaptCode, kaptdaCnt, recent_trade, is_apt, build_year) "
            "VALUES ('APT002', '구형아파트', '역삼동', 37.495, 127.025,"
            " 'R08333C28422', 'K001', 300.0, 3, 1, 1980)"
        )
        full_db.execute(
            "INSERT INTO trade_recent "
            "(apt_seq, pyeong_type, pyeong, floor, deal_amount_int, deal_year, deal_month, deal_day, dealing_gbn) "
            "VALUES ('APT002', '20평대', 25.0, 5, 20000, 2026, 4, 10, '중개거래')"
        )
        full_db.commit()
        data = self._post(full_client, {'build_year_min': 1960}).json()
        seqs = [c['apt_seq'] for c in data['cards']]
        assert 'APT002' in seqs


# ── min_price 필터 케이스 ───────────────────────────────────────

class TestMinPriceFilter:
    """min_price 파라미터 필터링 검증 (spec-09).

    시드 데이터: APT001, deal_amount_int=30000 (3억).
    """

    def _post(self, client, extra=None):
        payload = {
            'workplace_address': '강남역',
            'max_minutes': 60,
            'max_price': 100000,
            'pyeong_types': ['20평대'],
        }
        if extra:
            payload.update(extra)
        with (
            patch('app.search.get_or_create', return_value=_FAKE_WP),
        ):
            return client.post('/api/search', json=payload)

    # ── AC1 ────────────────────────────────────────────────────

    def test_min_price_excludes_cheaper_cards(self, full_client):
        """AC1: min_price=35000 (3.5억) → seed 거래가 30000 제외 → cards 빈 배열."""
        data = self._post(full_client, {'min_price': 35000}).json()
        assert data['cards'] == []

    def test_min_price_inclusive_boundary(self, full_client):
        """min_price == 거래가(30000) 이면 포함 (>= 이므로)."""
        data = self._post(full_client, {'min_price': 30000}).json()
        assert len(data['cards']) >= 1

    def test_min_price_below_trade_includes(self, full_client):
        """min_price < 거래가 → 포함됨."""
        data = self._post(full_client, {'min_price': 25000}).json()
        assert len(data['cards']) >= 1

    # ── AC2 (회귀) ─────────────────────────────────────────────

    def test_min_price_none_no_regression(self, full_client):
        """AC2: min_price 미지정 → 기존 동작 유지 (카드 존재)."""
        data = self._post(full_client).json()
        assert len(data['cards']) >= 1

    # ── AC3 ────────────────────────────────────────────────────

    def test_min_price_equal_to_max_returns_422(self, full_client):
        """AC3: min_price == max_price → 422."""
        r = self._post(full_client, {'min_price': 100000, 'max_price': 100000})
        assert r.status_code == 422

    def test_min_price_greater_than_max_returns_422(self, full_client):
        """AC3 변형: min_price > max_price → 422."""
        r = self._post(full_client, {'min_price': 110000, 'max_price': 100000})
        assert r.status_code == 422


# ── apt_walking_poi 미존재 graceful (POI 정렬 가드) ──────────────

class TestPoiTableMissingGraceful:
    """apt_walking_poi 테이블이 없어도 검색이 500 없이 정상 동작."""

    def _client_without_poi(self):
        from app.main import app
        from app.db import get_db
        conn = sqlite3.connect(':memory:', check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.executescript(_FULL_SCHEMA)
        _seed_db(conn)
        conn.execute('DROP TABLE apt_walking_poi')
        conn.commit()

        def _override():
            yield conn

        app.dependency_overrides[get_db] = _override
        from fastapi.testclient import TestClient
        return TestClient(app), conn

    def _post(self, client):
        with (
            patch('app.search.get_or_create', return_value=_FAKE_WP),
        ):
            return client.post('/api/search', json={
                'workplace_address': '강남역', 'max_minutes': 60,
                'max_price': 50000, 'pyeong_types': ['20평대'],
            })

    def test_returns_200_without_poi_table(self):
        from app.main import app
        c, conn = self._client_without_poi()
        try:
            with c:
                resp = self._post(c)
        finally:
            app.dependency_overrides.clear()
            conn.close()
        assert resp.status_code == 200
        assert len(resp.json()['cards']) >= 1
