"""
tests/test_detail_endpoint.py — GET /api/apt/{apt_seq}/detail 단위 테스트

Spec 10: search.py L600~826 커버리지 확보
- 건물정보(building_info), 시세차트, POI, 동 비교, 친구 한 마디
- 미존재 단지 → {} 반환
- price_summary: 7개월 이상 → change_6m_pct 계산, 미만 → None
"""
import sqlite3
import pytest
from fastapi.testclient import TestClient

# ── 스키마 ─────────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS apartments (
    apt_seq   TEXT,
    apt_nm    TEXT,
    umd_nm    TEXT,
    kaptdaCnt REAL,
    lat       REAL,
    lng       REAL,
    kaptCode  TEXT,
    grid_key  TEXT,
    is_apt    INTEGER NOT NULL DEFAULT 0,
    build_year INTEGER
);

CREATE TABLE IF NOT EXISTS kapt_complexes (
    kaptCode                TEXT PRIMARY KEY,
    kaptUsedate             TEXT,
    kaptTopFloor            INTEGER,
    kaptBaseFloor           INTEGER,
    kaptDongCnt             INTEGER,
    kaptdEcnt               INTEGER,
    kaptdCccnt              INTEGER,
    kaptdPcnt               TEXT,
    kaptdPcntu              TEXT,
    codeHeatNm              TEXT,
    codeHallNm              TEXT,
    kaptBcompany            TEXT,
    groundElChargerCnt      INTEGER,
    undergroundElChargerCnt INTEGER,
    subwayLine              TEXT,
    subwayStation           TEXT,
    kaptdWtimesub           INTEGER
);

CREATE TABLE IF NOT EXISTS trade_history (
    apt_seq         TEXT,
    pyeong_type     TEXT,
    pyeong          REAL,
    deal_year       INTEGER,
    deal_month      INTEGER,
    deal_day        INTEGER,
    deal_amount_int INTEGER,
    floor           INTEGER,
    umd_nm          TEXT
);
CREATE TABLE IF NOT EXISTS trade_recent (
    apt_seq         TEXT,
    pyeong_type     TEXT,
    pyeong          REAL,
    deal_year       INTEGER,
    deal_month      INTEGER,
    deal_day        INTEGER,
    deal_amount_int INTEGER,
    floor           INTEGER,
    dealing_gbn     TEXT
);

CREATE TABLE IF NOT EXISTS apt_pt_friend_comment (
    apt_seq     TEXT,
    pyeong_type TEXT,
    wp_id       INTEGER,
    comment     TEXT,
    PRIMARY KEY (apt_seq, pyeong_type, wp_id)
);

CREATE TABLE IF NOT EXISTS apt_walking_poi (
    kaptCode     TEXT,
    poi_lclas_cd TEXT,
    poi_mlsfc_cd TEXT,
    poi_nm       TEXT,
    distance_m   REAL,
    walking_min  INTEGER
);

CREATE TABLE IF NOT EXISTS apt_slope (
    kaptCode      TEXT PRIMARY KEY,
    apt_slope_avg REAL
);

CREATE TABLE IF NOT EXISTS building_register (
    kaptCode     TEXT,
    mgmBldrgstPk TEXT,
    vlRat        REAL,
    bcRat        REAL,
    strctCdNm    TEXT,
    useAprDay    TEXT
);

CREATE TABLE IF NOT EXISTS workplaces (
    wp_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    address_key  TEXT NOT NULL UNIQUE,
    address_input TEXT,
    address_norm TEXT,
    b_code       TEXT NOT NULL DEFAULT '',
    main_bun     TEXT,
    sub_bun      TEXT,
    lat          REAL,
    lng          REAL,
    folder_name  TEXT,
    first_seen   TEXT,
    last_used    TEXT,
    search_count INTEGER NOT NULL DEFAULT 0,
    cells_cached INTEGER NOT NULL DEFAULT 0
);
"""


def _seed(conn):
    """기본 시드 데이터 — APT001/KC001/역삼동."""
    # apartments
    conn.execute(
        "INSERT INTO apartments (apt_seq,apt_nm,umd_nm,kaptdaCnt,lat,lng,kaptCode,grid_key) "
        "VALUES (?,?,?,?,?,?,?,?)",
        ('APT001', '역삼레미안', '역삼동', 500, 37.5, 127.0, 'KC001', 'G001'),
    )
    # kapt_complexes
    conn.execute(
        "INSERT INTO kapt_complexes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ('KC001', '20040517', 20, 1, 5, 10, 200, '100', '50',
         '개별난방', '계단식', '삼성물산', 3, 2, '2호선', '역삼역', 5),
    )
    # trade_history — 8개월치 (price_summary 계산용)
    months = [
        (2023, 9,  80000), (2023, 10, 82000), (2023, 11, 83000), (2023, 12, 85000),
        (2024, 1,  87000), (2024, 2,  89000), (2024, 3,  90000), (2024, 4,  95000),
    ]
    for y, m, price in months:
        conn.execute(
            "INSERT INTO trade_history "
            "(apt_seq,pyeong_type,pyeong,deal_year,deal_month,deal_day,deal_amount_int,floor,umd_nm) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            ('APT001', '20평대', 20, y, m, 1, price, 5, '역삼동'),
        )
    # friend_comment — 길이 다른 2건
    conn.execute(
        "INSERT INTO apt_pt_friend_comment (apt_seq,pyeong_type,wp_id,comment) VALUES (?,?,?,?)",
        ('APT001', '20평대', 1, '짧은 코멘트'),
    )
    conn.execute(
        "INSERT INTO apt_pt_friend_comment (apt_seq,pyeong_type,wp_id,comment) VALUES (?,?,?,?)",
        ('APT001', '30평대', 1, '이것은 훨씬 더 길고 상세한 코멘트입니다'),
    )
    # POI
    for cat, sub, name, dist, walk in [
        ('D', 'D01', '역삼역 3번출구', 200, 3),
        ('F', 'F01', '역삼병원',       350, 5),
        ('E', 'E01', 'GS25 역삼점',     100, 2),
    ]:
        conn.execute(
            "INSERT INTO apt_walking_poi "
            "(kaptCode,poi_lclas_cd,poi_mlsfc_cd,poi_nm,distance_m,walking_min) "
            "VALUES (?,?,?,?,?,?)",
            ('KC001', cat, sub, name, dist, walk),
        )
    # apt_slope (spec-31) — 평지 케이스
    conn.execute(
        "INSERT INTO apt_slope (kaptCode, apt_slope_avg) VALUES (?,?)",
        ('KC001', 2.0),
    )
    # building_register (spec-31) — 동 2개 (AVG/MIN/최빈값 집계 검증)
    for pk, far in (('KC001-1', 237.0), ('KC001-2', 243.0)):
        conn.execute(
            "INSERT INTO building_register "
            "(kaptCode,mgmBldrgstPk,vlRat,bcRat,strctCdNm,useAprDay) "
            "VALUES (?,?,?,?,?,?)",
            ('KC001', pk, far, 22.0, '철근콘크리트구조', '20040517'),
        )
    conn.commit()


@pytest.fixture
def detail_db():
    conn = sqlite3.connect(':memory:', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    _seed(conn)
    yield conn
    conn.close()


@pytest.fixture
def detail_client(detail_db):
    from app.main import app
    from app.db import get_db

    def _override():
        yield detail_db

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── 기본 구조 ─────────────────────────────────────────────────

class TestDetailBasic:
    def test_returns_200(self, detail_client):
        resp = detail_client.get('/api/apt/APT001/detail?wp_id=1')
        assert resp.status_code == 200

    def test_top_level_fields_present(self, detail_client):
        data = detail_client.get('/api/apt/APT001/detail?wp_id=1').json()
        for field in ('apt_seq', 'apt_nm', 'umd_nm', 'building',
                      'pyeong_tabs', 'chart', 'trades', 'poi', 'price_summary'):
            assert field in data, f'missing field: {field}'

    def test_unknown_apt_returns_empty(self, detail_client):
        resp = detail_client.get('/api/apt/NOEXIST/detail?wp_id=1')
        assert resp.status_code == 200
        assert resp.json() == {}


# ── building_info ─────────────────────────────────────────────

class TestBuildingInfo:
    def test_build_year_parsed_from_kaptUsedate(self, detail_client):
        data = detail_client.get('/api/apt/APT001/detail?wp_id=1').json()
        assert data['building']['build_year'] == 2004

    def test_parking_total_sum(self, detail_client):
        # kaptdCccnt=200, kaptdPcntu=50 → total=250
        data = detail_client.get('/api/apt/APT001/detail?wp_id=1').json()
        assert data['building']['parking'] == 250

    def test_ev_chargers_sum(self, detail_client):
        # groundElChargerCnt=3, undergroundElChargerCnt=2 → 5
        data = detail_client.get('/api/apt/APT001/detail?wp_id=1').json()
        assert data['building']['ev_chargers'] == 5

    def test_top_floor(self, detail_client):
        data = detail_client.get('/api/apt/APT001/detail?wp_id=1').json()
        assert data['building']['top_floor'] == 20

    def test_heat_type(self, detail_client):
        data = detail_client.get('/api/apt/APT001/detail?wp_id=1').json()
        assert data['building']['heat_type'] == '개별난방'

    def test_subway_info(self, detail_client):
        data = detail_client.get('/api/apt/APT001/detail?wp_id=1').json()
        bi = data['building']
        assert bi['subway_line'] == '2호선'
        assert bi['subway_sta'] == '역삼역'


# ── 친구 한 마디 ──────────────────────────────────────────────

class TestFriendComment:
    def test_returns_longest_comment(self, detail_client):
        data = detail_client.get('/api/apt/APT001/detail?wp_id=1').json()
        assert data['friend_comment'] == '이것은 훨씬 더 길고 상세한 코멘트입니다'

    def test_no_comment_returns_none(self, detail_client, detail_db):
        # APT002는 코멘트 없음
        detail_db.execute(
            "INSERT INTO apartments (apt_seq,apt_nm,umd_nm,kaptdaCnt,lat,lng,kaptCode,grid_key) "
            "VALUES (?,?,?,?,?,?,?,?)",
            ('APT002', '테스트', '테스트동', 100, 37.5, 127.1, None, None),
        )
        detail_db.commit()
        data = detail_client.get('/api/apt/APT002/detail?wp_id=1').json()
        assert data.get('friend_comment') is None

    def test_wrong_wp_id_returns_none(self, detail_client):
        # wp_id=999 → 해당 코멘트 없음
        data = detail_client.get('/api/apt/APT001/detail?wp_id=999').json()
        assert data.get('friend_comment') is None


# ── POI ───────────────────────────────────────────────────────

class TestPOI:
    def test_poi_list_returned(self, detail_client):
        data = detail_client.get('/api/apt/APT001/detail?wp_id=1').json()
        assert isinstance(data['poi'], list)
        assert len(data['poi']) == 3

    def test_poi_sorted_by_distance(self, detail_client):
        data = detail_client.get('/api/apt/APT001/detail?wp_id=1').json()
        dists = [p['distance_m'] for p in data['poi']]
        assert dists == sorted(dists)

    def test_poi_fields(self, detail_client):
        data = detail_client.get('/api/apt/APT001/detail?wp_id=1').json()
        poi = data['poi'][0]
        for f in ('category', 'sub_category', 'name', 'distance_m', 'walking_min'):
            assert f in poi


# ── price_summary ─────────────────────────────────────────────

class TestPriceSummary:
    def test_change_6m_pct_calculated_with_7months(self, detail_client):
        data = detail_client.get('/api/apt/APT001/detail?wp_id=1').json()
        ps = data['price_summary']
        # months_sorted[-1]=95000(2024-04), months_sorted[-7]=82000(2023-10)
        # round((95000-82000)/82000*100, 1) = 15.9
        assert ps['change_6m_pct'] is not None
        assert ps['change_6m_pct'] == pytest.approx(15.9, abs=0.2)

    def test_change_6m_pct_none_when_less_than_7months(self, detail_client, detail_db):
        # APT003 — 5개월만 데이터
        detail_db.execute(
            "INSERT INTO apartments (apt_seq,apt_nm,umd_nm,kaptdaCnt,lat,lng,kaptCode,grid_key) "
            "VALUES (?,?,?,?,?,?,?,?)",
            ('APT003', '부족한아파트', '역삼동', 100, 37.5, 127.2, None, None),
        )
        for y, m, price in [(2024,1,80000),(2024,2,82000),(2024,3,83000),(2024,4,85000),(2024,5,87000)]:
            detail_db.execute(
                "INSERT INTO trade_history "
                "(apt_seq,pyeong_type,pyeong,deal_year,deal_month,deal_day,deal_amount_int,floor,umd_nm) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                ('APT003', '20평대', 20, y, m, 1, price, 5, '역삼동'),
            )
        detail_db.commit()
        data = detail_client.get('/api/apt/APT003/detail?wp_id=1').json()
        assert data['price_summary'].get('change_6m_pct') is None

    def test_price_summary_pyeong_type(self, detail_client):
        data = detail_client.get('/api/apt/APT001/detail?wp_id=1').json()
        assert data['price_summary']['pyeong_type'] == '20평대'


# ── 거래 내역 ─────────────────────────────────────────────────

class TestTrades:
    def test_trades_list_returned(self, detail_client):
        data = detail_client.get('/api/apt/APT001/detail?wp_id=1').json()
        assert isinstance(data['trades'], list)
        assert len(data['trades']) == 8

    def test_trades_sorted_desc(self, detail_client):
        data = detail_client.get('/api/apt/APT001/detail?wp_id=1').json()
        # 최신 거래가 먼저
        first = data['trades'][0]
        assert first['date'].startswith('2024')


# ── 입지·구조 지표 (spec-31) ──────────────────────────────────

class TestSlopeLabelHelpers:
    """경사/용적률/건폐율/승인일 라벨 변환 순수함수."""

    def test_slope_label_flat(self):
        from app.search import _slope_label
        assert _slope_label(2.0) == ('평지', '걷기 편해요', 1)

    def test_slope_label_gentle(self):
        from app.search import _slope_label
        assert _slope_label(5.0)[0] == '완만한 오르막'
        assert _slope_label(5.0)[2] == 2

    def test_slope_label_hill(self):
        from app.search import _slope_label
        assert _slope_label(9.0)[0] == '언덕'
        assert _slope_label(9.0)[2] == 3

    def test_slope_label_steep(self):
        from app.search import _slope_label
        assert _slope_label(13.0)[0] == '가파른 언덕'
        assert _slope_label(13.0)[2] == 4

    def test_slope_label_negative_treated_flat(self):
        from app.search import _slope_label
        assert _slope_label(-1.0)[0] == '평지'

    def test_slope_label_none(self):
        from app.search import _slope_label
        assert _slope_label(None) is None

    def test_far_levels(self):
        from app.search import _far_level
        assert _far_level(160) == '낮은 편'
        assert _far_level(240) == '보통'
        assert _far_level(300) == '높은 편'
        assert _far_level(0) is None

    def test_bcr_levels(self):
        from app.search import _bcr_level
        assert _bcr_level(12) == '낮은 편'
        assert _bcr_level(20) == '보통'
        assert _bcr_level(30) == '높은 편'

    def test_approve_ym(self):
        from app.search import _approve_ym
        assert _approve_ym('20040517') == '2004.05'
        assert _approve_ym('2004') is None
        assert _approve_ym('20041350') is None  # 월 13 비정상
        assert _approve_ym(None) is None


class TestInfraSection:
    """detail building 객체의 입지·구조 필드."""

    def test_slope_fields_present(self, detail_client):
        b = detail_client.get('/api/apt/APT001/detail?wp_id=1').json()['building']
        assert b['slope_label'] == '평지'
        assert b['slope_hint'] == '걷기 편해요'
        assert b['slope_avg'] == 2.0
        assert b['slope_level'] == 1

    def test_far_bcr_aggregated(self, detail_client):
        b = detail_client.get('/api/apt/APT001/detail?wp_id=1').json()['building']
        assert b['far'] == 240.0          # (237+243)/2
        assert b['far_level'] == '보통'
        assert b['bcr'] == 22.0
        assert b['bcr_level'] == '보통'

    def test_structure_and_approve(self, detail_client):
        b = detail_client.get('/api/apt/APT001/detail?wp_id=1').json()['building']
        assert b['structure'] == '철근콘크리트구조'
        assert b['approve_ym'] == '2004.05'

    def test_missing_tables_graceful(self):
        """apt_slope/building_register 미존재 → 500 없이 상세 정상."""
        conn = sqlite3.connect(':memory:', check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.executescript(_SCHEMA)
        _seed(conn)
        conn.execute('DROP TABLE apt_slope')
        conn.execute('DROP TABLE building_register')
        conn.commit()
        from app.main import app
        from app.db import get_db

        def _ov():
            yield conn

        app.dependency_overrides[get_db] = _ov
        with TestClient(app) as c:
            resp = c.get('/api/apt/APT001/detail?wp_id=1')
        app.dependency_overrides.clear()
        conn.close()
        assert resp.status_code == 200
        b = resp.json()['building']
        assert 'slope_label' not in b
        assert 'far' not in b
