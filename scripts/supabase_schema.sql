-- =============================================================
-- Supabase(Postgres) 스키마 — real_estate 앱 런타임 필수 테이블
--
-- 사용법:
--   1. Supabase 대시보드 → SQL Editor → 이 파일 전체 붙여넣기 → Run
--   2. scripts/migrate_sqlite_to_supabase.py 로 데이터 이관
--
-- 주의: 대용량 테이블(apartments / trade_history / trade_recent / kapt_complexes)
--   먼저 데이터 INSERT한 다음 인덱스 생성하면 훨씬 빠름. 이 파일은 schema만.
-- =============================================================

-- ── workplaces ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS workplaces (
    wp_id          SERIAL PRIMARY KEY,
    address_key    TEXT NOT NULL UNIQUE,
    address_input  TEXT,
    address_norm   TEXT,
    b_code         TEXT NOT NULL,
    main_bun       TEXT,
    sub_bun        TEXT,
    lat            DOUBLE PRECISION,
    lng            DOUBLE PRECISION,
    folder_name    TEXT,
    first_seen     TEXT,
    last_used      TEXT,
    search_count   INTEGER NOT NULL DEFAULT 0,
    cells_cached   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_wp_last_used ON workplaces(last_used DESC);


-- ── apartments ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS apartments (
    apt_seq                  TEXT,
    apt_nm                   TEXT,
    sgg_cd                   TEXT,
    road_nm                  TEXT,
    road_nm_bonbun           TEXT,
    road_nm_bubun            TEXT,
    umd_nm                   TEXT,
    lat                      DOUBLE PRECISION,
    lng                      DOUBLE PRECISION,
    grid_key                 TEXT,
    geocoded                 INTEGER,
    "kaptCode"               TEXT,
    "kaptName"               TEXT,
    "kaptAddr"               TEXT,
    "doroJuso"               TEXT,
    "kaptdaCnt"              DOUBLE PRECISION,
    "ktownFlrNo"             INTEGER,
    "kaptBaseFloor"          INTEGER,
    "kaptMparea60"           DOUBLE PRECISION,
    "kaptMparea85"           DOUBLE PRECISION,
    "kaptMparea135"          DOUBLE PRECISION,
    "kaptMparea136"          DOUBLE PRECISION,
    "kaptBcompany"           TEXT,
    "kaptdPcnt"              TEXT,
    "kaptdPcntu"             TEXT,
    "kaptdCccnt"             INTEGER,
    "groundElChargerCnt"     INTEGER,
    "undergroundElChargerCnt" INTEGER,
    recent_trade             INTEGER,
    "codeAptNm"              TEXT,
    is_apt                   INTEGER NOT NULL DEFAULT 0,
    building_type            TEXT
);
CREATE INDEX IF NOT EXISTS idx_apt_seq      ON apartments(apt_seq);
CREATE INDEX IF NOT EXISTS idx_apt_kapt     ON apartments("kaptCode");
CREATE INDEX IF NOT EXISTS idx_apt_grid     ON apartments(grid_key);
CREATE INDEX IF NOT EXISTS idx_apt_grid_rt  ON apartments(grid_key, recent_trade);
CREATE INDEX IF NOT EXISTS idx_apt_is_apt   ON apartments(is_apt);
CREATE INDEX IF NOT EXISTS idx_apt_recent   ON apartments(recent_trade);
CREATE INDEX IF NOT EXISTS idx_apt_aptnm    ON apartments("codeAptNm");


-- ── kapt_complexes ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS kapt_complexes (
    "kaptCode"               TEXT PRIMARY KEY,
    "kaptName"               TEXT,
    "bjdCode"                TEXT,
    as1 TEXT, as2 TEXT, as3 TEXT, as4 TEXT,
    "kaptAddr"               TEXT,
    "doroJuso"               TEXT,
    zipcode                  TEXT,
    "codeSaleNm"             TEXT,
    "codeHeatNm"             TEXT,
    "codeAptNm"              TEXT,
    "codeMgrNm"              TEXT,
    "codeHallNm"             TEXT,
    "kaptUsedate"            TEXT,
    "kaptdaCnt"              DOUBLE PRECISION,
    "hoCnt"                  INTEGER,
    "kaptDongCnt"            INTEGER,
    "kaptTopFloor"           INTEGER,
    "ktownFlrNo"             INTEGER,
    "kaptBaseFloor"          INTEGER,
    "kaptdEcntp"             INTEGER,
    "kaptTarea"              DOUBLE PRECISION,
    "kaptMarea"              DOUBLE PRECISION,
    "privArea"               DOUBLE PRECISION,
    "kaptMparea60"           DOUBLE PRECISION,
    "kaptMparea85"           DOUBLE PRECISION,
    "kaptMparea135"          DOUBLE PRECISION,
    "kaptMparea136"          DOUBLE PRECISION,
    "kaptBcompany"           TEXT,
    "kaptAcompany"           TEXT,
    "kaptTel"                TEXT,
    "kaptFax"                TEXT,
    "kaptUrl"                TEXT,
    "codeMgr"                TEXT,
    "kaptMgrCnt"             TEXT,
    "kaptCcompany"           TEXT,
    "codeSec"                TEXT,
    "kaptdScnt"              TEXT,
    "kaptdSecCom"            TEXT,
    "codeClean"              TEXT,
    "kaptdClcnt"             TEXT,
    "codeGarbage"            TEXT,
    "codeDisinf"             TEXT,
    "kaptdDcnt"              TEXT,
    "disposalType"           TEXT,
    "codeStr"                TEXT,
    "kaptdEcapa"             TEXT,
    "codeEcon"               TEXT,
    "codeEmgr"               TEXT,
    "codeFalarm"             TEXT,
    "codeWsupply"            TEXT,
    "codeElev"               TEXT,
    "kaptdEcnt"              INTEGER,
    "kaptdPcnt"              TEXT,
    "kaptdPcntu"             TEXT,
    "codeNet"                TEXT,
    "kaptdCccnt"             INTEGER,
    "welfareFacility"        TEXT,
    "kaptdWtimebus"          TEXT,
    "subwayLine"             TEXT,
    "subwayStation"          TEXT,
    "kaptdWtimesub"          TEXT,
    "convenientFacility"     TEXT,
    "educationFacility"      TEXT,
    "groundElChargerCnt"     INTEGER,
    "undergroundElChargerCnt" INTEGER,
    "useYn"                  TEXT,
    fetched_at               TEXT
);
CREATE INDEX IF NOT EXISTS idx_kapt_bjd ON kapt_complexes("bjdCode");


-- ── trade_recent / trade_history (스키마 동일) ───────────────
CREATE TABLE IF NOT EXISTS trade_recent (
    id INTEGER,
    apt_nm TEXT, apt_dong TEXT, apt_seq TEXT,
    build_year INTEGER,
    deal_year INTEGER, deal_month INTEGER, deal_day INTEGER,
    deal_amount TEXT, deal_amount_int INTEGER,
    exclu_use_ar DOUBLE PRECISION,
    pyeong_type TEXT, pyeong INTEGER, floor INTEGER,
    road_nm TEXT, road_nm_bonbun TEXT, road_nm_bubun TEXT,
    road_nm_cd TEXT, road_nm_seq TEXT, road_nm_sgg_cd TEXT, road_nmb_cd TEXT,
    umd_nm TEXT, umd_cd TEXT,
    bonbun TEXT, bubun TEXT, jibun TEXT, land_cd TEXT, sgg_cd TEXT,
    buyer_gbn TEXT, sler_gbn TEXT, dealing_gbn TEXT,
    estate_agent_sggnm TEXT, land_leasehold_gbn TEXT,
    cdeal_day TEXT, cdeal_type TEXT, rgst_date TEXT, lawd_cd TEXT
);
CREATE INDEX IF NOT EXISTS idx_tr_apt_seq        ON trade_recent(apt_seq);
CREATE INDEX IF NOT EXISTS idx_tr_pyeong         ON trade_recent(pyeong_type);
CREATE INDEX IF NOT EXISTS idx_tr_amount         ON trade_recent(apt_seq, exclu_use_ar, deal_year, deal_month);
CREATE INDEX IF NOT EXISTS idx_tr_apt_amount_py  ON trade_recent(apt_seq, deal_amount_int, pyeong_type);
CREATE INDEX IF NOT EXISTS idx_tr_search         ON trade_recent(pyeong_type, deal_amount_int, apt_seq);

CREATE TABLE IF NOT EXISTS trade_history (
    id INTEGER,
    apt_nm TEXT, apt_dong TEXT, apt_seq TEXT,
    build_year INTEGER,
    deal_year INTEGER, deal_month INTEGER, deal_day INTEGER,
    deal_amount TEXT, deal_amount_int INTEGER,
    exclu_use_ar DOUBLE PRECISION,
    pyeong_type TEXT, pyeong INTEGER, floor INTEGER,
    road_nm TEXT, road_nm_bonbun TEXT, road_nm_bubun TEXT,
    road_nm_cd TEXT, road_nm_seq TEXT, road_nm_sgg_cd TEXT, road_nmb_cd TEXT,
    umd_nm TEXT, umd_cd TEXT,
    bonbun TEXT, bubun TEXT, jibun TEXT, land_cd TEXT, sgg_cd TEXT,
    buyer_gbn TEXT, sler_gbn TEXT, dealing_gbn TEXT,
    estate_agent_sggnm TEXT, land_leasehold_gbn TEXT,
    cdeal_day TEXT, cdeal_type TEXT, rgst_date TEXT, lawd_cd TEXT
);
CREATE INDEX IF NOT EXISTS idx_th_apt_seq    ON trade_history(apt_seq);
CREATE INDEX IF NOT EXISTS idx_th_pyeong     ON trade_history(pyeong_type);
CREATE INDEX IF NOT EXISTS idx_th_apt_py_ym  ON trade_history(apt_seq, pyeong_type, deal_year, deal_month);
CREATE INDEX IF NOT EXISTS idx_th_sgg_py_ym  ON trade_history(sgg_cd, pyeong_type, deal_year, deal_month);
CREATE INDEX IF NOT EXISTS idx_th_umd_py_ym  ON trade_history(umd_nm, pyeong_type, deal_year, deal_month);


-- ── apt_walking_poi / apt_hsmp_mapping / apt_slope ───────────
CREATE TABLE IF NOT EXISTS apt_walking_poi (
    id              SERIAL PRIMARY KEY,
    "kaptCode"      TEXT NOT NULL,
    poi_lclas_cd    TEXT,
    poi_mlsfc_cd    TEXT,
    poi_nm          TEXT,
    distance_m      DOUBLE PRECISION,
    walking_min     INTEGER
);
CREATE INDEX IF NOT EXISTS idx_awp_kapt     ON apt_walking_poi("kaptCode");
CREATE INDEX IF NOT EXISTS idx_awp_kapt_cat ON apt_walking_poi("kaptCode", poi_lclas_cd);

CREATE TABLE IF NOT EXISTS apt_hsmp_mapping (
    "kaptCode"  TEXT PRIMARY KEY,
    hsmp_innb   TEXT NOT NULL,
    pnu         TEXT,
    nm_csv      TEXT,
    nm_db       TEXT,
    nmhsh_csv   INTEGER,
    nmhsh_db    INTEGER,
    matched_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_ahm_hsmp ON apt_hsmp_mapping(hsmp_innb);

CREATE TABLE IF NOT EXISTS apt_slope (
    "kaptCode"     TEXT PRIMARY KEY,
    apt_slope_avg  DOUBLE PRECISION,
    apt_slope_low  DOUBLE PRECISION,
    apt_slope_top  DOUBLE PRECISION,
    ngbr_slope_avg DOUBLE PRECISION,
    ngbr_slope_low DOUBLE PRECISION,
    ngbr_slope_top DOUBLE PRECISION
);


-- ── grid_cells ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS grid_cells (
    cell_code   TEXT PRIMARY KEY,
    row_idx     INTEGER NOT NULL,
    col_idx     INTEGER NOT NULL,
    center_lat  DOUBLE PRECISION NOT NULL,
    center_lng  DOUBLE PRECISION NOT NULL,
    lat_min     DOUBLE PRECISION NOT NULL,
    lat_max     DOUBLE PRECISION NOT NULL,
    lng_min     DOUBLE PRECISION NOT NULL,
    lng_max     DOUBLE PRECISION NOT NULL,
    active      INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_gc_active ON grid_cells(active);


-- ── transit_cache / transit_routes ───────────────────────────
CREATE TABLE IF NOT EXISTS transit_cache (
    origin_cell    TEXT    NOT NULL,
    wp_id          INTEGER NOT NULL,
    total_time     INTEGER,
    bus_cnt        INTEGER,
    subway_cnt     INTEGER,
    walk_total     INTEGER,
    passed_filter  INTEGER NOT NULL,
    path_idx       INTEGER,
    raw_file       TEXT,
    response_size  INTEGER,
    fetched_at     TEXT,
    PRIMARY KEY (origin_cell, wp_id)
);
CREATE INDEX IF NOT EXISTS idx_tc_wp     ON transit_cache(wp_id);
CREATE INDEX IF NOT EXISTS idx_tc_passed ON transit_cache(wp_id, passed_filter);

CREATE TABLE IF NOT EXISTS transit_routes (
    origin_cell     TEXT    NOT NULL,
    wp_id           INTEGER NOT NULL,
    rank            INTEGER NOT NULL,
    total_time_min  INTEGER NOT NULL,
    bus_cnt         INTEGER NOT NULL,
    subway_cnt      INTEGER NOT NULL,

    step1_type      TEXT NOT NULL DEFAULT '',
    step1_time_min  INTEGER, step1_dist_m INTEGER,
    "step1_노선"    TEXT NOT NULL DEFAULT '',
    "step1_출발"    TEXT NOT NULL DEFAULT '',
    "step1_도착"    TEXT NOT NULL DEFAULT '',

    step2_type      TEXT NOT NULL DEFAULT '',
    step2_time_min  INTEGER, step2_dist_m INTEGER,
    "step2_노선"    TEXT NOT NULL DEFAULT '',
    "step2_출발"    TEXT NOT NULL DEFAULT '',
    "step2_도착"    TEXT NOT NULL DEFAULT '',

    step3_type      TEXT NOT NULL DEFAULT '',
    step3_time_min  INTEGER, step3_dist_m INTEGER,
    "step3_노선"    TEXT NOT NULL DEFAULT '',
    "step3_출발"    TEXT NOT NULL DEFAULT '',
    "step3_도착"    TEXT NOT NULL DEFAULT '',

    step4_type      TEXT NOT NULL DEFAULT '',
    step4_time_min  INTEGER, step4_dist_m INTEGER,
    "step4_노선"    TEXT NOT NULL DEFAULT '',
    "step4_출발"    TEXT NOT NULL DEFAULT '',
    "step4_도착"    TEXT NOT NULL DEFAULT '',

    step5_type      TEXT NOT NULL DEFAULT '',
    step5_time_min  INTEGER, step5_dist_m INTEGER,
    "step5_노선"    TEXT NOT NULL DEFAULT '',
    "step5_출발"    TEXT NOT NULL DEFAULT '',
    "step5_도착"    TEXT NOT NULL DEFAULT '',

    PRIMARY KEY (origin_cell, wp_id, rank)
);
CREATE INDEX IF NOT EXISTS idx_tr_main      ON transit_routes(wp_id, rank, total_time_min);
CREATE INDEX IF NOT EXISTS idx_tr_origin_wp ON transit_routes(origin_cell, wp_id);
CREATE INDEX IF NOT EXISTS idx_tr_wp        ON transit_routes(wp_id);


-- ── 친구 한 마디 캐시 ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS apt_friend_comment (
    apt_seq     TEXT NOT NULL,
    wp_id       INTEGER NOT NULL,
    tier        TEXT NOT NULL,
    comment     TEXT NOT NULL,
    model       TEXT DEFAULT 'claude-haiku-4-5',
    created_at  TIMESTAMP DEFAULT now(),
    PRIMARY KEY (apt_seq, wp_id)
);

CREATE TABLE IF NOT EXISTS apt_pt_friend_comment (
    apt_seq      TEXT NOT NULL,
    pyeong_type  TEXT NOT NULL,
    wp_id        INTEGER NOT NULL,
    comment      TEXT NOT NULL,
    model        TEXT DEFAULT 'claude-haiku-4-5',
    created_at   TIMESTAMP DEFAULT now(),
    PRIMARY KEY (apt_seq, pyeong_type, wp_id)
);


-- ── building_register (런타임 미사용이나 호환성 유지) ─────────
CREATE TABLE IF NOT EXISTS building_register (
    "kaptCode"       TEXT NOT NULL,
    "mgmBldrgstPk"   TEXT NOT NULL,
    "dongNm"         TEXT,
    "mainPurpsCdNm"  TEXT,
    "etcPurps"       TEXT,
    "hhldCnt"        INTEGER,
    "grndFlrCnt"     INTEGER,
    "ugrndFlrCnt"    INTEGER,
    "totArea"        DOUBLE PRECISION,
    "archArea"       DOUBLE PRECISION,
    "platArea"       DOUBLE PRECISION,
    "bcRat"          DOUBLE PRECISION,
    "vlRat"          DOUBLE PRECISION,
    heit             DOUBLE PRECISION,
    "strctCdNm"      TEXT,
    "useAprDay"      TEXT,
    fetched_at       TEXT,
    PRIMARY KEY ("kaptCode", "mgmBldrgstPk")
);
CREATE INDEX IF NOT EXISTS idx_br_kapt  ON building_register("kaptCode");
CREATE INDEX IF NOT EXISTS idx_br_purps ON building_register("mainPurpsCdNm");

CREATE TABLE IF NOT EXISTS building_register_log (
    "kaptCode"   TEXT PRIMARY KEY,
    status       TEXT,
    row_count    INTEGER,
    fetched_at   TEXT
);

-- ── trade_tags — 추천 카드 "저가 근거" 사전 계산 태그 ───────────
CREATE TABLE IF NOT EXISTS trade_tags (
    apt_seq     TEXT,
    pyeong_type TEXT,
    tag_type    TEXT,   -- 'floor' | 'price_chg'
    label       TEXT,   -- UI 표시 문구 (12자 이내)
    detail      TEXT,   -- 툴팁용 보조 설명 (nullable)
    calc_date   TEXT,   -- ISO 8601
    PRIMARY KEY (apt_seq, pyeong_type, tag_type)
);
