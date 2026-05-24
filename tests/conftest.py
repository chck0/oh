# !! 반드시 모든 app import 전에 env 설정 !!
# config.py 는 _Config 클래스 정의 시점(import 시)에 _require('KAKAO_REST_API_KEY')를 호출함.
# transit.py 는 모듈 상단에서 cfg.ODSAY_KEYS 를 접근함.
import os
os.environ.setdefault('KAKAO_REST_API_KEY', 'test-kakao-key')
os.environ.setdefault('ODSAY_KEY_1', 'test-odsay-key')
os.environ.setdefault('ODSAY_REFERER_1', 'http://test.local')
os.environ.setdefault('ANTHROPIC_API_KEY', 'test-anthropic-key')

import sqlite3
import pytest

# ── In-memory DB 스키마 (런타임에 필요한 테이블만) ──────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS workplaces (
    wp_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    address_key  TEXT NOT NULL UNIQUE,
    address_input TEXT,
    address_norm TEXT,
    b_code       TEXT NOT NULL,
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

CREATE TABLE IF NOT EXISTS trade_recent (
    apt_seq      TEXT,
    pyeong_type  TEXT,
    price_low    INTEGER,
    price_high   INTEGER,
    deal_count   INTEGER,
    deal_year_month INTEGER
);

CREATE TABLE IF NOT EXISTS trade_history (
    apt_seq      TEXT,
    deal_year    INTEGER,
    deal_month   INTEGER,
    deal_price   INTEGER,
    pyeong_type  TEXT
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
    apt_pt_key TEXT PRIMARY KEY,
    comment    TEXT,
    kind       TEXT,
    created_at TEXT
);
"""


@pytest.fixture
def mem_db():
    """In-memory SQLite DB + 전체 스키마. 테스트마다 새로 생성."""
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    yield conn
    conn.close()


@pytest.fixture
def client(mem_db):
    """FastAPI TestClient — get_db 의존성을 in-memory DB로 교체."""
    from app.main import app
    from app.db import get_db

    def _override():
        yield mem_db

    app.dependency_overrides[get_db] = _override
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
