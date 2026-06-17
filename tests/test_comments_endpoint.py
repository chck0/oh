"""
tests/test_comments_endpoint.py — GET /api/comments + GET /api/apt/{apt_seq}/routes

Spec 10: search.py L422~590 커버리지 확보
- comments 폴링: 캐시 히트/미스, keys 200개 초과 400, wp_id 필터, 잘못된 키 무시
- routes: 정상 경로 반환, 미존재 apt → options: []
"""
import sqlite3
import pytest
from fastapi.testclient import TestClient

_SCHEMA = """
CREATE TABLE IF NOT EXISTS workplaces (
    wp_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    address_key  TEXT NOT NULL UNIQUE,
    address_input TEXT,
    address_norm TEXT,
    b_code       TEXT NOT NULL DEFAULT '',
    lat REAL, lng REAL,
    main_bun TEXT, sub_bun TEXT, folder_name TEXT,
    first_seen TEXT, last_used TEXT,
    search_count INTEGER NOT NULL DEFAULT 0,
    cells_cached INTEGER NOT NULL DEFAULT 0
);

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

CREATE TABLE IF NOT EXISTS apt_pt_friend_comment (
    apt_seq     TEXT,
    pyeong_type TEXT,
    wp_id       INTEGER,
    comment     TEXT,
    PRIMARY KEY (apt_seq, pyeong_type, wp_id)
);

CREATE TABLE IF NOT EXISTS transit_routes (
    origin_cell    TEXT    NOT NULL,
    wp_id          INTEGER NOT NULL,
    rank           INTEGER NOT NULL,
    total_time_min INTEGER NOT NULL,
    bus_cnt        INTEGER NOT NULL,
    subway_cnt     INTEGER NOT NULL,
    step1_type TEXT NOT NULL DEFAULT '',
    step1_time_min INTEGER, step1_dist_m INTEGER,
    "step1_노선" TEXT NOT NULL DEFAULT '',
    "step1_출발" TEXT NOT NULL DEFAULT '',
    "step1_도착" TEXT NOT NULL DEFAULT '',
    "step1_linestring" TEXT,
    step2_type TEXT NOT NULL DEFAULT '',
    step2_time_min INTEGER, step2_dist_m INTEGER,
    "step2_노선" TEXT NOT NULL DEFAULT '',
    "step2_출발" TEXT NOT NULL DEFAULT '',
    "step2_도착" TEXT NOT NULL DEFAULT '',
    "step2_linestring" TEXT,
    step3_type TEXT NOT NULL DEFAULT '',
    step3_time_min INTEGER, step3_dist_m INTEGER,
    "step3_노선" TEXT NOT NULL DEFAULT '',
    "step3_출발" TEXT NOT NULL DEFAULT '',
    "step3_도착" TEXT NOT NULL DEFAULT '',
    "step3_linestring" TEXT,
    step4_type TEXT NOT NULL DEFAULT '',
    step4_time_min INTEGER, step4_dist_m INTEGER,
    "step4_노선" TEXT NOT NULL DEFAULT '',
    "step4_출발" TEXT NOT NULL DEFAULT '',
    "step4_도착" TEXT NOT NULL DEFAULT '',
    "step4_linestring" TEXT,
    step5_type TEXT NOT NULL DEFAULT '',
    step5_time_min INTEGER, step5_dist_m INTEGER,
    "step5_노선" TEXT NOT NULL DEFAULT '',
    "step5_출발" TEXT NOT NULL DEFAULT '',
    "step5_도착" TEXT NOT NULL DEFAULT '',
    "step5_linestring" TEXT,
    PRIMARY KEY (origin_cell, wp_id, rank)
);
"""


def _seed(conn):
    # 코멘트 캐시 — wp_id=1
    conn.execute(
        "INSERT INTO apt_pt_friend_comment VALUES (?,?,?,?)",
        ('APT001', '20평대', 1, '역삼동 직통 아파트'),
    )
    conn.execute(
        "INSERT INTO apt_pt_friend_comment VALUES (?,?,?,?)",
        ('APT002', '30평대', 1, '강남 30평대'),
    )
    # 다른 wp_id의 코멘트 (wp_id=2)
    conn.execute(
        "INSERT INTO apt_pt_friend_comment VALUES (?,?,?,?)",
        ('APT003', '20평대', 2, 'wp2 전용 코멘트'),
    )
    # 경로 테스트용 apartment + transit_routes
    conn.execute(
        "INSERT INTO apartments (apt_seq,apt_nm,umd_nm,kaptdaCnt,lat,lng,kaptCode,grid_key) "
        "VALUES (?,?,?,?,?,?,?,?)",
        ('RAPT001', '경로테스트', '역삼동', 200, 37.5, 127.0, None, 'G001'),
    )
    conn.execute(
        """INSERT INTO transit_routes
           (origin_cell, wp_id, rank, total_time_min, bus_cnt, subway_cnt,
            step1_type, step1_time_min, step1_dist_m, "step1_노선", "step1_출발", "step1_도착",
            step2_type, step2_time_min, step2_dist_m, "step2_노선", "step2_출발", "step2_도착",
            step3_type, step3_time_min, step3_dist_m, "step3_노선", "step3_출발", "step3_도착",
            step4_type, step4_time_min, step4_dist_m, "step4_노선", "step4_출발", "step4_도착",
            step5_type, step5_time_min, step5_dist_m, "step5_노선", "step5_출발", "step5_도착")
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        ('G001', 1, 1, 25, 0, 1,
         '지하철', 20, 500, '2호선', '역삼역', '강남역',
         '도보', 5, 300, '', '', '',
         '', None, None, '', '', '',
         '', None, None, '', '', '',
         '', None, None, '', '', ''),
    )
    conn.commit()


@pytest.fixture
def cmt_db():
    conn = sqlite3.connect(':memory:', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    _seed(conn)
    yield conn
    conn.close()


@pytest.fixture
def cmt_client(cmt_db):
    from app.main import app
    from app.db import get_db

    def _override():
        yield cmt_db

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── GET /api/comments ─────────────────────────────────────────

class TestGetComments:
    def test_cache_hit_returns_comment(self, cmt_client):
        resp = cmt_client.get('/api/comments?wp_id=1&keys=APT001:20평대')
        assert resp.status_code == 200
        data = resp.json()
        assert 'APT001:20평대' in data
        assert data['APT001:20평대']['comment'] == '역삼동 직통 아파트'

    def test_multiple_keys(self, cmt_client):
        resp = cmt_client.get('/api/comments?wp_id=1&keys=APT001:20평대,APT002:30평대')
        data = resp.json()
        assert len(data) == 2
        assert 'APT001:20평대' in data
        assert 'APT002:30평대' in data

    def test_cache_miss_returns_empty(self, cmt_client):
        resp = cmt_client.get('/api/comments?wp_id=1&keys=NOEXIST:20평대')
        assert resp.status_code == 200
        assert resp.json() == {}

    def test_too_many_keys_returns_400(self, cmt_client):
        keys = ','.join([f'APT{i:03d}:20평대' for i in range(201)])
        resp = cmt_client.get(f'/api/comments?wp_id=1&keys={keys}')
        assert resp.status_code == 400

    def test_malformed_key_without_colon_ignored(self, cmt_client):
        # ':' 없는 키는 무시, 나머지는 정상 처리
        resp = cmt_client.get('/api/comments?wp_id=1&keys=BADKEY,APT001:20평대')
        assert resp.status_code == 200
        data = resp.json()
        assert 'APT001:20평대' in data

    def test_wp_id_filter_works(self, cmt_client):
        # wp_id=2의 코멘트는 wp_id=1로 조회 시 안 보임
        resp = cmt_client.get('/api/comments?wp_id=1&keys=APT003:20평대')
        assert resp.json() == {}

    def test_wp_id_2_sees_own_comment(self, cmt_client):
        resp = cmt_client.get('/api/comments?wp_id=2&keys=APT003:20평대')
        data = resp.json()
        assert 'APT003:20평대' in data
        assert data['APT003:20평대']['comment'] == 'wp2 전용 코멘트'

    def test_empty_keys_returns_empty(self, cmt_client):
        resp = cmt_client.get('/api/comments?wp_id=1&keys=')
        assert resp.status_code == 200
        assert resp.json() == {}


# ── GET /api/apt/{apt_seq}/routes ─────────────────────────────

class TestGetRoutes:
    def test_routes_returned_for_known_apt(self, cmt_client):
        resp = cmt_client.get('/api/apt/RAPT001/routes?wp_id=1')
        assert resp.status_code == 200
        data = resp.json()
        assert data['apt_seq'] == 'RAPT001'
        assert data['wp_id'] == 1
        assert len(data['options']) == 1

    def test_route_fields(self, cmt_client):
        data = cmt_client.get('/api/apt/RAPT001/routes?wp_id=1').json()
        opt = data['options'][0]
        assert opt['rank'] == 1
        assert opt['total_time_min'] == 25
        assert isinstance(opt['steps'], list)
        assert len(opt['steps']) >= 1

    def test_unknown_apt_returns_empty_options(self, cmt_client):
        resp = cmt_client.get('/api/apt/NOEXIST/routes?wp_id=1')
        assert resp.status_code == 200
        data = resp.json()
        assert data['options'] == []

    def test_apt_without_grid_key_returns_empty_options(self, cmt_client, cmt_db):
        # grid_key=None인 apt는 routes 없음
        cmt_db.execute(
            "INSERT INTO apartments (apt_seq,apt_nm,umd_nm,kaptdaCnt,lat,lng,kaptCode,grid_key) "
            "VALUES (?,?,?,?,?,?,?,?)",
            ('NOGRID', '그리드없는아파트', '동', 100, 37.5, 127.0, None, None),
        )
        cmt_db.commit()
        resp = cmt_client.get('/api/apt/NOGRID/routes?wp_id=1')
        data = resp.json()
        assert data['options'] == []
