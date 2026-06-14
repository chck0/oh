# !! 반드시 모든 app import 전에 env 설정 !!
# config.py 는 _Config 클래스 정의 시점(import 시)에 _require('KAKAO_REST_API_KEY')를 호출함.
# transit.py 는 모듈 상단에서 cfg.ODSAY_KEYS 를 접근함.
import os
os.environ.setdefault('KAKAO_REST_API_KEY', 'test-kakao-key')
os.environ.setdefault('ODSAY_KEY_1', 'test-odsay-key')
os.environ.setdefault('ODSAY_REFERER_1', 'http://test.local')
os.environ.setdefault('ANTHROPIC_API_KEY', 'test-anthropic-key')
# 테스트는 항상 SQLite 모드로 강제 — .env의 DATABASE_URL(실 Supabase)을 절대 안 침.
# config.py가 load_dotenv(override=False)로 .env를 읽으므로, 여기서 빈 값을
# 먼저 박아두면(override=False라 덮어쓰지 않음) USE_PG=False가 보장된다.
os.environ['DATABASE_URL'] = ''
os.environ['SUPABASE_DB_URL'] = ''

import sqlite3
import pytest


class _SharedConn:
    """공유 SQLite 커넥션 래퍼.

    search.py가 병렬 쿼리(_fetch_card_extras / apt_detail의 _q_*)에서
    db_connect()를 직접 호출하는데, close()로 공유 conn을 닫으면 안 되므로
    close()를 no-op 처리. 나머지는 위임.
    """
    def __init__(self, conn):
        self._c = conn

    def execute(self, *a, **k):
        return self._c.execute(*a, **k)

    def executemany(self, *a, **k):
        return self._c.executemany(*a, **k)

    def cursor(self, *a, **k):
        return self._c.cursor(*a, **k)

    def commit(self):
        return self._c.commit()

    def rollback(self):
        return self._c.rollback()

    def close(self):
        pass  # 공유 conn — 닫지 않음

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
    "step5_노선" TEXT, "step5_출발" TEXT, "step5_도착" TEXT,
    step1_linestring TEXT, step2_linestring TEXT, step3_linestring TEXT,
    step4_linestring TEXT, step5_linestring TEXT
);

CREATE TABLE IF NOT EXISTS apt_pt_friend_comment (
    apt_pt_key TEXT PRIMARY KEY,
    comment    TEXT,
    kind       TEXT,
    created_at TEXT
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


@pytest.fixture
def mem_db():
    """In-memory SQLite DB + 전체 스키마. 테스트마다 새로 생성.

    check_same_thread=False: search.py 병렬 쿼리가 asyncio.to_thread로
    별도 스레드에서 같은 conn을 쓰므로 필요 (SQLite는 SERIALIZED 모드라 안전).
    """
    conn = sqlite3.connect(':memory:', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def _clear_module_caches():
    """테스트 간 모듈 레벨 캐시 초기화.

    main.py lifespan의 _warm_caches()가 파일 SQLite로 _apt_cache / _col_cache를
    빈 값으로 채울 수 있다. autouse로 매 테스트 전후에 리셋해 캐시 오염을 방지.
    """
    import app.search as _s
    import app.portable as _p

    def _reset():
        _s._apt_cache['rows'] = None
        _s._apt_cache['ts'] = 0.0
        _p._col_cache.clear()

    _reset()
    yield
    _reset()


@pytest.fixture(autouse=True)
def _route_db_connect_to_override():
    """search.py의 직접 db_connect() 호출을 get_db 오버라이드와 같은 conn으로 라우팅.

    search.py의 _fetch_card_extras / apt_detail은 (프로덕션에선 풀 병렬 쿼리를
    위해) db_connect()를 직접 호출하여 의존성 주입을 우회한다. 테스트에서는
    get_db 오버라이드가 가리키는 동일 conn을 쓰도록 app.search.db_connect를
    몽키패치한다. 오버라이드가 없으면 원래 db_connect로 폴백.

    모든 테스트 conn은 check_same_thread=False라 asyncio.to_thread 접근 안전.
    autouse라 get_db를 오버라이드하는 모든 테스트 파일에 자동 적용.
    """
    from app.main import app
    from app.db import get_db
    import app.search as search_mod
    import app.detail as detail_mod

    # _fetch_card_extras는 search.py, apt_detail은 detail.py에서 db_connect()를
    # 직접 호출한다. 두 모듈 모두 동일 override conn으로 라우팅해야 함.
    orig_search = search_mod.db_connect
    orig_detail = detail_mod.db_connect

    def _routed():
        override = app.dependency_overrides.get(get_db)
        if override is None:
            return orig_search()
        gen = override()
        conn = next(gen)
        return _SharedConn(conn)

    search_mod.db_connect = _routed
    detail_mod.db_connect = _routed
    try:
        yield
    finally:
        search_mod.db_connect = orig_search
        detail_mod.db_connect = orig_detail


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
