"""
초등학교 도보 POI 적재 (Spec 29)

NEIS 초등학교(서울/경기/인천) → Kakao 지오코딩 → 단지별 도보 15분(1100m) 거리계산
→ apt_walking_poi 에 중·고와 동일 형식(poi_lclas_cd='A', poi_mlsfc_cd='A01')으로 멱등 적재.

멱등성: 적재 전
    DELETE FROM apt_walking_poi WHERE poi_lclas_cd='A' AND poi_mlsfc_cd='A01'
                                  AND poi_nm LIKE '%초등학교%'
로 '우리가 넣은 초등학교 행'만 제거 후 재삽입 (중·고는 초등학교 패턴 불일치 → 안전).

사용법:
    python scripts/fetch_elementary_poi.py                 # 전체 적재
    python scripts/fetch_elementary_poi.py --limit 10      # 단지 10개만 (테스트)
    python scripts/fetch_elementary_poi.py --dry-run       # DB 미반영, 통계만
    python scripts/fetch_elementary_poi.py --refresh-geocode  # 지오코딩 캐시 무시
"""
import sys
import json
import math
import time
import argparse
import urllib.request
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import cfg                       # noqa: E402
from app.db import connect                   # noqa: E402

# Windows 콘솔(cp949)에서 한글/em-dash 출력 크래시 방지
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")  # type: ignore[union-attr]
except Exception:
    pass

# ── 상수 (Spec 29 결정사항) ──────────────────────────────────────
REGIONS       = ["서울특별시", "경기도", "인천광역시"]
DIST_LIMIT_M  = 1100                          # 도보 15분
WALK_M_PER_MIN = 75                           # 기존 중·고 데이터 역산값
# 학교 카테고리는 lclas='A'(=화면 라벨 "학교"). 기존 A 서브코드: A01=중학교,
# A02=고등학교, A03=대학. 초등학교는 전용 코드 'A04'로 넣어 멱등 DELETE를
# 이름 무관하게 정확히 수행("○○초"처럼 '초등학교' 글자 없는 경우 대비).
ELEM_MLSFC    = "A04"
CACHE_PATH    = cfg.PROJECT_ROOT / "data" / "raw" / "neis_elem.json"
NEIS_URL      = "https://open.neis.go.kr/hub/schoolInfo"
KAKAO_URL     = "https://dapi.kakao.com/v2/local/search/address.json"
GRID_DEG      = 0.02                          # ~2.2km 셀 (1100m < 셀 → 3x3 이웃이 안전)


def _log(msg: str) -> None:
    print(msg, flush=True)


# ── 1) NEIS 초등학교 수집 ────────────────────────────────────────
def fetch_neis_schools() -> list[dict]:
    """서울/경기/인천 초등학교 목록(이름+도로명주소). 페이징."""
    key = cfg.NEIS_API_KEY
    if not key:
        raise SystemExit("[config] NEIS_API_KEY 누락 — .env 확인")
    schools: list[dict] = []
    for sido in REGIONS:
        page = 1
        while True:
            params = {
                "KEY": key, "Type": "json", "pIndex": page, "pSize": 1000,
                "SCHUL_KND_SC_NM": "초등학교", "LCTN_SC_NM": sido,
            }
            url = NEIS_URL + "?" + urllib.parse.urlencode(params)
            req = urllib.request.Request(url, headers={"User-Agent": "badugi-poi/1.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read().decode("utf-8"))
            if "schoolInfo" not in data:
                break
            rows = data["schoolInfo"][1]["row"]
            for s in rows:
                addr = (s.get("ORG_RDNMA") or "").strip()
                nm = (s.get("SCHUL_NM") or "").strip()
                if not nm or not addr:
                    continue
                schools.append({
                    "name": nm, "addr": addr, "sido": sido,
                    "sd_code": s.get("SD_SCHUL_CODE"),
                    "lat": None, "lng": None,
                })
            if len(rows) < 1000:
                break
            page += 1
    _log(f"[NEIS] 초등학교 {len(schools)}개 수집 (서울/경기/인천)")
    return schools


# ── 2) Kakao 지오코딩 ────────────────────────────────────────────
def geocode(addr: str) -> tuple[float, float] | None:
    """도로명주소 → (lat, lng). 실패 시 None."""
    params = urllib.parse.urlencode({"query": addr})
    req = urllib.request.Request(
        f"{KAKAO_URL}?{params}",
        headers={"Authorization": f"KakaoAK {cfg.KAKAO_REST_API_KEY}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        _log(f"  [geocode 실패] {addr}: {type(e).__name__}")
        return None
    docs = data.get("documents", [])
    if not docs:
        return None
    d = docs[0]
    ra = d.get("road_address") or {}
    y = ra.get("y") or d.get("y")
    x = ra.get("x") or d.get("x")
    if not (x and y):
        return None
    return float(y), float(x)


def load_or_build_schools(refresh_geocode: bool = False) -> list[dict]:
    """캐시 활용. NEIS 수집 + 미지오코딩분만 지오코딩."""
    if CACHE_PATH.exists():
        schools = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        _log(f"[cache] {CACHE_PATH.name} 로드 ({len(schools)}개)")
    else:
        schools = fetch_neis_schools()
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(schools, ensure_ascii=False, indent=1), encoding="utf-8")

    todo = [s for s in schools if refresh_geocode or s.get("lat") is None]
    if todo:
        _log(f"[geocode] {len(todo)}개 지오코딩 시작...")
        ok = fail = 0
        for i, s in enumerate(todo, 1):
            coord = geocode(s["addr"])
            if coord:
                s["lat"], s["lng"] = coord
                ok += 1
            else:
                fail += 1
            if i % 200 == 0:
                _log(f"  ...{i}/{len(todo)} (성공 {ok}/실패 {fail})")
                CACHE_PATH.write_text(json.dumps(schools, ensure_ascii=False, indent=1), encoding="utf-8")
            time.sleep(0.03)  # rate limit 여유
        CACHE_PATH.write_text(json.dumps(schools, ensure_ascii=False, indent=1), encoding="utf-8")
        _log(f"[geocode] 완료 — 성공 {ok} / 실패 {fail}")
    geocoded = [s for s in schools if s.get("lat") is not None]
    _log(f"[schools] 좌표 보유 {len(geocoded)}/{len(schools)}개")
    return geocoded


# ── 3) 거리계산 (그리드 버킷으로 최적화) ─────────────────────────
def haversine_m(lat1, lng1, lat2, lng2) -> float:
    R = 6371000.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlng / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def _cell(lat, lng) -> tuple[int, int]:
    return (int(lat / GRID_DEG), int(lng / GRID_DEG))


def build_rows(apartments: list[dict], schools: list[dict]) -> list[tuple]:
    """각 단지 도보 1100m 이내 초등학교 → INSERT 행 리스트."""
    grid: dict[tuple, list[dict]] = {}
    for s in schools:
        grid.setdefault(_cell(s["lat"], s["lng"]), []).append(s)

    rows: list[tuple] = []
    for apt in apartments:
        alat, alng, kapt = apt["lat"], apt["lng"], apt["kaptCode"]
        if alat is None or alng is None or not kapt:
            continue
        ci, cj = _cell(alat, alng)
        seen = set()
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for s in grid.get((ci + di, cj + dj), []):
                    d = haversine_m(alat, alng, s["lat"], s["lng"])
                    if d <= DIST_LIMIT_M and s["name"] not in seen:
                        seen.add(s["name"])
                        rows.append((
                            kapt, "A", ELEM_MLSFC, s["name"],
                            round(d, 1), round(d / WALK_M_PER_MIN),
                        ))
    return rows


# ── 4) 멱등 적재 ─────────────────────────────────────────────────
def load_apartments(conn, limit: int | None) -> list[dict]:
    sql = "SELECT kaptCode, lat, lng FROM apartments WHERE lat IS NOT NULL AND lng IS NOT NULL"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [dict(kaptCode=r["kaptCode"], lat=r["lat"], lng=r["lng"])
            for r in conn.execute(sql).fetchall()]


def upsert(conn, rows: list[tuple]) -> None:
    # 멱등: 우리 전용 코드(A04) 행 전량 제거 — 이름과 무관하게 정확.
    conn.execute(
        "DELETE FROM apt_walking_poi WHERE poi_lclas_cd='A' AND poi_mlsfc_cd=?",
        (ELEM_MLSFC,),
    )
    # 마이그레이션: 과거 실수로 A01(중학교 코드)에 들어간 초등학교 행 정리.
    # 초등학교 이름 집합과 일치하는 A01 행만 제거 (중학교 이름은 불일치 → 안전).
    names = sorted({r[3] for r in rows})
    if names:
        conn.execute(
            "DELETE FROM apt_walking_poi "
            "WHERE poi_lclas_cd='A' AND poi_mlsfc_cd='A01' AND poi_nm = ANY(?)",
            (names,),
        )
    # id 컬럼이 serial이 아닐 수 있어 max+1부터 수동 할당 (양 DB 안전)
    maxid = conn.execute("SELECT COALESCE(MAX(id), 0) FROM apt_walking_poi").fetchone()[0]
    payload = [(maxid + i + 1, *row) for i, row in enumerate(rows)]
    conn.executemany(
        "INSERT INTO apt_walking_poi "
        "(id, kaptCode, poi_lclas_cd, poi_mlsfc_cd, poi_nm, distance_m, walking_min) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        payload,
    )
    conn.commit()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="단지 N개만 (테스트)")
    ap.add_argument("--dry-run", action="store_true", help="DB 미반영, 통계만")
    ap.add_argument("--refresh-geocode", action="store_true", help="지오코딩 캐시 무시")
    args = ap.parse_args()

    schools = load_or_build_schools(refresh_geocode=args.refresh_geocode)
    if not schools:
        raise SystemExit("좌표 보유 학교 0개 — 중단")

    conn = connect()
    try:
        apts = load_apartments(conn, args.limit)
        _log(f"[apartments] 대상 단지 {len(apts)}개")
        rows = build_rows(apts, schools)
        dmax = max((r[4] for r in rows), default=0)
        _log(f"[rows] 적재 대상 {len(rows)}건 (거리 max {dmax}m)")

        if args.dry_run:
            _log("[dry-run] DB 미반영. 샘플 5건:")
            for r in rows[:5]:
                _log(f"  {r[0]} | {r[3]} | {r[4]}m | 도보 {r[5]}분")
            return

        upsert(conn, rows)
        cnt = conn.execute(
            "SELECT COUNT(*) FROM apt_walking_poi "
            "WHERE poi_lclas_cd='A' AND poi_mlsfc_cd=?", (ELEM_MLSFC,)
        ).fetchone()[0]
        _log(f"[done] 적재 완료 — 초등학교 POI {cnt}건 (A/{ELEM_MLSFC})")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
