"""
seed_demo_data.py — 로컬 데모 모드용 시드 데이터 생성 (spec-32)

API 키·운영 데이터 없이 전체 화면 플로우(검색→추천→상세→경로)를 로컬에서
확인할 수 있도록 강남역 직장(wp_id=1) 기준 가상 단지 데이터를 SQLite에 넣는다.

- 모든 단지는 가상이며 apt_seq가 DEMO 접두사로 시작한다.
- transit_cache를 passed_filter=1로 채워 검색 시 ODsay 호출이 발생하지 않는다.
- 친구 코멘트를 사전 시드해 ANTHROPIC_API_KEY 없이도 llm_pending=false가 된다.
- 멱등: 재실행 시 DEMO 행과 wp_id=1을 지우고 다시 넣는다.

사용법:
    python scripts/seed_demo_data.py
    BADUGI_DEMO=1 uvicorn app.main:app --port 8000
"""
import os
import sys
import sqlite3
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# config는 import 시점에 KAKAO 키를 요구 — 데모 시드는 키가 없어도 돌아야 한다
os.environ.setdefault('KAKAO_REST_API_KEY', 'demo')
os.environ.setdefault('ODSAY_KEY_1', 'demo')
os.environ.setdefault('ODSAY_REFERER_1', 'http://localhost:8000')

if os.getenv('DATABASE_URL') or os.getenv('SUPABASE_DB_URL'):
    sys.exit('[seed_demo] DATABASE_URL이 설정되어 있습니다. '
             '데모 시드는 로컬 SQLite 전용입니다 — 운영 DB 보호를 위해 중단합니다.')

from config import cfg                  # noqa: E402
from app.transit import cell_of         # noqa: E402

_SCHEMA = """
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
    pyeong_type     TEXT,
    pyeong          REAL,
    deal_year       INTEGER,
    deal_month      INTEGER,
    deal_day        INTEGER,
    deal_amount_int INTEGER,
    floor           INTEGER,
    umd_nm          TEXT
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
    apt_seq      TEXT NOT NULL,
    pyeong_type  TEXT NOT NULL,
    wp_id        INTEGER NOT NULL,
    comment      TEXT NOT NULL,
    model        TEXT DEFAULT 'claude-haiku-4-5',
    created_at   TEXT DEFAULT (datetime('now','localtime')),
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
CREATE TABLE IF NOT EXISTS apt_slope (
    kaptCode       TEXT PRIMARY KEY,
    apt_slope_avg  REAL,
    apt_slope_low  REAL,
    apt_slope_top  REAL,
    ngbr_slope_avg REAL,
    ngbr_slope_low REAL,
    ngbr_slope_top REAL
);
CREATE TABLE IF NOT EXISTS building_register (
    kaptCode     TEXT NOT NULL,
    mgmBldrgstPk TEXT NOT NULL,
    vlRat        REAL,
    bcRat        REAL,
    strctCdNm    TEXT,
    useAprDay    TEXT,
    PRIMARY KEY (kaptCode, mgmBldrgstPk)
);
"""

# 입지·구조 시드 (spec-31) — seq: (경사°, 용적률%, 건폐율%, 구조)
# 경사: 평지/완만/언덕/가파른언덕, 용적률/건폐율: 낮은편/보통/높은편 다양하게 분포
INFRA = {
    'DEMO001': (2.0, 240, 22, '철근콘크리트구조'),
    'DEMO002': (4.5, 210, 18, '철근콘크리트구조'),
    'DEMO003': (1.5, 270, 24, '철근콘크리트구조'),
    'DEMO004': (8.0, 190, 14, '철근콘크리트벽식구조'),
    'DEMO005': (3.5, 250, 20, '철근콘크리트구조'),
    'DEMO006': (13.0, 160, 12, '연와조'),
    'DEMO007': (6.0, 220, 19, '철근콘크리트구조'),
    'DEMO008': (1.0, 290, 26, '철근콘크리트구조'),
    'DEMO009': (5.0, 230, 21, '철근콘크리트구조'),
    'DEMO010': (9.5, 175, 13, '철근콘크리트구조'),
}

WP = {'lat': 37.4979, 'lng': 127.0276}  # 강남역

# 가상 단지 정의: (seq, 이름, 동, lat, lng, 준공, 세대수, 통근분,
#                  경로타입('sub'|'bus+sub'), {평형: 기준가(만원)})
COMPLEXES = [
    ('DEMO001', '바둑마을1단지', '역삼동', 37.4952, 127.0305, 2004, 850, 18,
     'sub', {'20평대': 78000, '30평대': 105000}),
    ('DEMO002', '한솔타운', '서초동', 37.4880, 127.0150, 2010, 620, 24,
     'sub', {'20평대': 69000}),
    ('DEMO003', '푸른숲아파트', '도곡동', 37.4830, 127.0480, 1998, 1300, 28,
     'sub', {'30평대': 98000}),
    ('DEMO004', '강변하늘채', '잠원동', 37.5120, 127.0110, 2016, 450, 35,
     'bus+sub', {'20평대': 60000, '30평대': 88000}),
    ('DEMO005', '미래도시2차', '대치동', 37.4940, 127.0620, 2001, 980, 38,
     'sub', {'30평대': 92000}),
    ('DEMO006', '동산맨션', '사당동', 37.4760, 126.9710, 1995, 380, 44,
     'sub', {'20평대': 52000}),
    ('DEMO007', '새봄아파트', '신림동', 37.4840, 126.9300, 2008, 720, 48,
     'bus+sub', {'20평대': 45000, '30평대': 62000}),
    ('DEMO008', '호수마을', '문정동', 37.4850, 127.1220, 2013, 1500, 46,
     'sub', {'20평대': 56000}),
    ('DEMO009', '들꽃단지', '상도동', 37.4990, 126.9480, 2019, 540, 52,
     'sub', {'20평대': 48000}),
    ('DEMO010', '큰나무아파트', '천호동', 37.5380, 127.1230, 1992, 860, 57,
     'bus+sub', {'30평대': 58000}),
]

# 카톡 톤 코멘트 (단지별 1개 대표 — 평형별 동일 사용)
COMMENTS = {
    'DEMO001': '18분 컷에 2호선 직통이면 출퇴근은 최고지. 근데 22년차라 수리비는 좀 잡아야 돼.',
    'DEMO002': '서초동에서 6억대면 가격은 괜찮은 편이야. 세대수 620이라 거래는 좀 한산할 수 있어.',
    'DEMO003': '1300세대 대단지라 관리비 효율 좋고 환금성도 낫지. 98년식이라 주차는 빡빡할 거야.',
    'DEMO004': '2016년식 신축급에 6억이면 가성비 좋네. 버스 환승 끼는 게 살짝 귀찮을 듯.',
    'DEMO005': '대치동 학원가 도보권은 확실한 메리트야. 9.2억이면 동네 평균보단 살짝 높아.',
    'DEMO006': '5.2억에 44분이면 무난한 선택지야. 380세대 소단지라 시세 흐름은 느린 편이야.',
    'DEMO007': '4.5억에 30평대 옵션까지 있는 게 강점이지. 48분 통근은 체감 좀 될 거야.',
    'DEMO008': '1500세대 대단지에 2013년식이면 밸런스 좋아. 잠실 생활권이라 인프라도 든든해.',
    'DEMO009': '2019년식 새 아파트가 4.8억이면 솔깃하지. 통근 52분은 각오하고 가야 돼.',
    'DEMO010': '5.8억에 30평대면 평단가는 제일 착해. 92년식 구축이라 재건축 얘기는 확인 필요해.',
}

POI_SETS = [
    ('D', 'D01', '지하철역 출구', 350, 5),
    ('A', 'A01', '동네중학교', 600, 9),
    ('B', 'B01', '햇살어린이집', 250, 4),
    ('E', 'E03', '큰마트', 400, 6),
    ('F', 'F01', '우리내과의원', 300, 5),
    ('I', 'I01', '동네근린공원', 500, 8),
]

PYEONG_AVG = {'20평대': 25.0, '30평대': 34.0}


def _routes_rows(cell, total_min, kind):
    """rank 1(대표) + rank 2(대안) 경로 행 생성."""
    rows = []
    if kind == 'sub':
        walk1, walk2 = 6, 5
        sub_t = total_min - walk1 - walk2
        rows.append((cell, 1, total_min, 0, 1,
                     '도보', walk1, 450, '', '', '',
                     '지하철', sub_t, sub_t * 600, '2호선', '단지앞역', '강남역',
                     '도보', walk2, 380, '', '', ''))
        rows.append((cell, 2, total_min + 7, 1, 1,
                     '도보', 4, 300, '', '', '',
                     '버스', 12, 3000, '간선버스', '단지앞', '환승센터',
                     '지하철', total_min - 16 + 7, (total_min - 16) * 550, '2호선', '환승역', '강남역'))
    else:  # bus + sub
        rows.append((cell, 1, total_min, 1, 1,
                     '버스', 14, 3500, '지선버스', '단지앞', '환승역',
                     '지하철', total_min - 19, (total_min - 19) * 600, '2호선', '환승역', '강남역',
                     '도보', 5, 400, '', '', ''))
        rows.append((cell, 2, total_min + 9, 2, 0,
                     '버스', 20, 5000, '간선버스', '단지앞', '환승센터',
                     '버스', total_min - 11 + 9, 6000, '광역버스', '환승센터', '강남역',
                     '도보', 0, 0, '', '', ''))
    return rows


def main():
    db_path = Path(cfg.DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)

    # 멱등: 기존 데모 행 제거
    conn.execute("DELETE FROM workplaces WHERE address_key='DEMO|gangnam|0'")
    for t in ('apartments', 'trade_recent', 'trade_history',
              'apt_pt_friend_comment', 'trade_tags'):
        conn.execute(f"DELETE FROM {t} WHERE apt_seq LIKE 'DEMO%'")
    conn.execute("DELETE FROM kapt_complexes WHERE kaptCode LIKE 'KDEMO%'")
    conn.execute("DELETE FROM apt_walking_poi WHERE kaptCode LIKE 'KDEMO%'")
    conn.execute("DELETE FROM apt_slope WHERE kaptCode LIKE 'KDEMO%'")
    conn.execute("DELETE FROM building_register WHERE kaptCode LIKE 'KDEMO%'")
    conn.execute('DELETE FROM transit_cache WHERE wp_id=1')
    conn.execute('DELETE FROM transit_routes WHERE wp_id=1')

    now = '2026-06-13 00:00:00'
    conn.execute(
        "INSERT INTO workplaces (wp_id, address_key, address_input, address_norm,"
        " b_code, main_bun, sub_bun, lat, lng, folder_name, first_seen, last_used,"
        " search_count, cells_cached) "
        "VALUES (1, 'DEMO|gangnam|0', '강남역', '서울 강남구 테헤란로 504',"
        " '1168010100', '858', '', ?, ?, 'wp_0001__demo', ?, ?, 1, 0)",
        (WP['lat'], WP['lng'], now, now))

    today = date.today()
    for (seq, nm, umd, lat, lng, built, cnt, t_min, kind, prices) in COMPLEXES:
        cell = cell_of(lat, lng)
        kapt = f'K{seq}'
        conn.execute(
            'INSERT INTO apartments (apt_seq, apt_nm, sgg_cd, umd_nm, lat, lng,'
            ' grid_key, kaptCode, kaptdaCnt, recent_trade, is_apt, build_year)'
            ' VALUES (?,?,?,?,?,?,?,?,?,3,1,?)',
            (seq, nm, '11680', umd, lat, lng, cell, kapt, float(cnt), built))
        conn.execute(
            'INSERT INTO kapt_complexes (kaptCode, kaptUsedate, kaptTopFloor,'
            ' kaptBaseFloor, kaptDongCnt, kaptdEcnt, kaptdCccnt, kaptdPcnt,'
            ' kaptdPcntu, codeHeatNm, codeHallNm, kaptBcompany,'
            ' groundElChargerCnt, undergroundElChargerCnt,'
            ' subwayLine, subwayStation, kaptdWtimesub)'
            ' VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (kapt, f'{built}0301', 15 + (cnt % 10), 2, max(cnt // 120, 3),
             cnt // 90, 4, str(int(cnt * 0.4)), str(int(cnt * 0.8)),
             '개별난방', '계단식', '데모건설', 2, 6, '2호선', '단지앞역', 7))

        conn.execute(
            'INSERT OR REPLACE INTO transit_cache (origin_cell, wp_id, total_time,'
            ' bus_cnt, subway_cnt, walk_total, passed_filter, path_idx,'
            ' raw_file, response_size, fetched_at)'
            ' VALUES (?,1,?,?,1,11,1,0,NULL,1000,?)',
            (cell, t_min, 1 if kind == 'bus+sub' else 0, now))
        for r in _routes_rows(cell, t_min, kind):
            conn.execute(
                'INSERT INTO transit_routes (origin_cell, wp_id, rank,'
                ' total_time_min, bus_cnt, subway_cnt,'
                ' step1_type, step1_time_min, step1_dist_m,'
                ' "step1_노선", "step1_출발", "step1_도착",'
                ' step2_type, step2_time_min, step2_dist_m,'
                ' "step2_노선", "step2_출발", "step2_도착",'
                ' step3_type, step3_time_min, step3_dist_m,'
                ' "step3_노선", "step3_출발", "step3_도착")'
                ' VALUES (?,1,' + ','.join(['?'] * 22) + ')',
                (r[0], *r[1:]))

        for pt, base in prices.items():
            py = PYEONG_AVG[pt]
            top = 15 + (cnt % 10)
            # 최근 3개월 거래 3건 (카드·상세용)
            recent = [
                (today.year, today.month, 5, base, 10),
                (today.year, today.month - 1 or 12, 18, int(base * 0.97), 4),
                (today.year, today.month - 2 or 12, 22, int(base * 1.02), top),
            ]
            for (y, m, d, amt, fl) in recent:
                if m <= 0:
                    y, m = y - 1, m + 12
                conn.execute(
                    'INSERT INTO trade_recent (apt_seq, pyeong_type, pyeong, floor,'
                    ' deal_amount_int, deal_year, deal_month, deal_day, dealing_gbn)'
                    ' VALUES (?,?,?,?,?,?,?,?,?)',
                    (seq, pt, py, fl, amt, y, m, d, '중개거래'))
            # 12개월 이력 (시세 차트 + 가격변동 배지: 최근 3개월 vs 4~9개월 전)
            drift = 0.04 if built >= 2010 else -0.04  # 신축 상승·구축 하락 추세
            for back in range(12):
                y, m = today.year, today.month - back
                while m <= 0:
                    y, m = y - 1, m + 12
                amt = int(base * (1 - drift * back / 12))
                conn.execute(
                    'INSERT INTO trade_history (apt_seq, pyeong_type, pyeong,'
                    ' deal_year, deal_month, deal_day, deal_amount_int, floor, umd_nm)'
                    ' VALUES (?,?,?,?,?,12,?,?,?)',
                    (seq, pt, py, y, m, amt, 5 + back % 10, umd))
            conn.execute(
                'INSERT OR REPLACE INTO apt_pt_friend_comment'
                ' (apt_seq, pyeong_type, wp_id, comment, model, created_at)'
                ' VALUES (?,?,1,?,?,?)',
                (seq, pt, COMMENTS[seq], 'demo-seed', now))

        for (cat, sub, poi_nm, dist, walk) in POI_SETS:
            conn.execute(
                'INSERT INTO apt_walking_poi (kaptCode, poi_lclas_cd, poi_mlsfc_cd,'
                ' poi_nm, distance_m, walking_min) VALUES (?,?,?,?,?,?)',
                (kapt, cat, sub, f'{umd} {poi_nm}', float(dist), walk))

        # 입지·구조 (spec-31): 경사 1행 + 건축물대장 2개 동(집계 동작 확인용)
        slope, far, bcr, strct = INFRA[seq]
        conn.execute(
            'INSERT INTO apt_slope (kaptCode, apt_slope_avg, apt_slope_low,'
            ' apt_slope_top, ngbr_slope_avg) VALUES (?,?,?,?,?)',
            (kapt, slope, max(slope - 1.5, 0), slope + 2.0, slope + 0.5))
        for di, fdelta in enumerate((-3, 3)):  # 동별 용적률 살짝 차이 → AVG 검증
            conn.execute(
                'INSERT INTO building_register (kaptCode, mgmBldrgstPk, vlRat,'
                ' bcRat, strctCdNm, useAprDay) VALUES (?,?,?,?,?,?)',
                (kapt, f'{kapt}-{di+1}', far + fdelta, bcr, strct, f'{built}0301'))

    # why-tags 샘플 (저가 근거)
    conn.execute(
        "INSERT OR REPLACE INTO trade_tags (apt_seq, pyeong_type, tag_type, label, detail)"
        " VALUES ('DEMO006', '20평대', 'floor', '저층 매물', '2층/15층')")
    conn.execute(
        "INSERT OR REPLACE INTO trade_tags (apt_seq, pyeong_type, tag_type, label, detail)"
        " VALUES ('DEMO010', '30평대', 'price_chg', '직전比 -5%', NULL)")

    conn.commit()
    n_apt = conn.execute("SELECT COUNT(*) FROM apartments WHERE apt_seq LIKE 'DEMO%'").fetchone()[0]
    n_tr = conn.execute("SELECT COUNT(*) FROM trade_recent WHERE apt_seq LIKE 'DEMO%'").fetchone()[0]
    conn.close()
    print(f'[seed_demo] 완료 — {db_path} (단지 {n_apt} · 거래 {n_tr})')
    print('[seed_demo] 실행: BADUGI_DEMO=1 uvicorn app.main:app --port 8000')
    print("[seed_demo] 검색 주소: '강남역'")


if __name__ == '__main__':
    main()
