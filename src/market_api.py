"""
market_api.py — FastAPI 백엔드 for VerifyHome 시세 AI 챗봇 + 실거래 파이프라인

실행:
    uvicorn src.market_api:app --reload --port 8000
"""

import asyncio
import math
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import anthropic

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

app = FastAPI(title="VerifyHome Market API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

APT_TRADE_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
DATA_GO_KR_API_KEY = os.environ.get("DATA_GO_KR_API_KEY")
JUSO_CONFIRM_KEY = os.environ.get("JUSO_CONFIRM_KEY")
JUSO_URL = "https://business.juso.go.kr/addrlink/addrLinkApi.do"

# 정적 JSON 파일 경로 (API 호출 불필요 — 하드코딩)
_SRC = os.path.dirname(__file__)
_SUBWAY_JSON           = os.path.join(_SRC, "subway_stations.json")
_SCHOOL_JSON           = os.path.join(_SRC, "elementary_schools.json")
_SECONDARY_SCHOOL_JSON = os.path.join(_SRC, "secondary_schools.json")
_HOSPITAL_JSON         = os.path.join(_SRC, "hospitals.json")
_PARK_JSON             = os.path.join(_SRC, "parks.json")
_HIGHWAY_IC_JSON       = os.path.join(_SRC, "highway_ics.json")
_DISAMENITY_JSON       = os.path.join(_SRC, "disamenities.json")
_LARGE_STORE_JSON      = os.path.join(_SRC, "large_stores.json")
_subway_coords_cache: list[tuple[float, float]] | None = None

# 서울 25개 구 LAWD_CD
LAWD_CD_MAP: dict[str, str] = {
    "종로구": "11110", "중구": "11140", "용산구": "11170",
    "성동구": "11200", "광진구": "11215", "동대문구": "11230",
    "중랑구": "11260", "성북구": "11290", "강북구": "11305",
    "도봉구": "11320", "노원구": "11350", "은평구": "11380",
    "서대문구": "11410", "마포구": "11440", "양천구": "11470",
    "강서구": "11500", "구로구": "11530", "금천구": "11545",
    "영등포구": "11560", "동작구": "11590", "관악구": "11620",
    "서초구": "11650", "강남구": "11680", "송파구": "11710",
    "강동구": "11740",
}


# ── Request/Response 스키마 ──

class DongData(BaseModel):
    name: str
    data: list[float]

class ChartStats(BaseModel):
    complex_change_pct: float
    dong_change_pct: float
    complex_vs_dong_pct: float
    latest_complex: float
    latest_dong: float

class ChartContext(BaseModel):
    address: str = ""
    size_pyeong: int = 30
    months: list[str] = []
    complex: list[float] = []
    dong: list[float] = []
    active_dongs: list[DongData] = []
    stats: ChartStats | None = None

class HistoryMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str

class ChatRequest(BaseModel):
    message: str
    context: ChartContext
    history: list[HistoryMessage] = []
    amenity_summary: str = ""  # 입지 분석 데이터 (반경 1km 내 생활편의 현황)

class ChatResponse(BaseModel):
    reply: str


# ── 실거래 API 헬퍼 ──

def get_last_n_months(n: int = 6) -> list[str]:
    """최근 n개의 완료된 월 YYYYMM 목록 (당월 제외)"""
    today = datetime.today()
    months = []
    for i in range(n, 0, -1):
        month = today.month - i
        year = today.year
        while month <= 0:
            month += 12
            year -= 1
        months.append(f"{year}{month:02d}")
    return months


def parse_address(address: str) -> tuple[str, str, str | None]:
    """
    주소 문자열 → (lawd_cd, apt_name, dong_name)
    예) '강남구 역삼래미안' → ('11680', '역삼래미안', None)
        '역삼동 래미안아파트' → ('11680', '래미안아파트', '역삼동')  # 동 → 강남구 default
    """
    lawd_cd = "11680"  # gu 미인식 시 강남구 기본값
    remaining = address.strip()

    for gu, cd in LAWD_CD_MAP.items():
        if gu in remaining:
            lawd_cd = cd
            remaining = remaining.replace(gu, "").strip()
            break

    dong_name: str | None = None
    dong_match = re.search(r"(\S+동)", remaining)
    if dong_match:
        dong_name = dong_match.group(1)
        remaining = remaining.replace(dong_name, "").strip()

    # "서울시", "서울특별시" 등 불필요한 접두사 제거
    remaining = re.sub(r"^서울(특별)?시?\s*", "", remaining).strip()
    apt_name = remaining or address.strip()

    return lawd_cd, apt_name, dong_name


async def fetch_month_items(lawd_cd: str, deal_ymd: str) -> list[dict]:
    """단일 월 실거래 데이터 fetch → 정제된 항목 리스트 반환"""
    if not DATA_GO_KR_API_KEY:
        return []

    params = {
        "serviceKey": DATA_GO_KR_API_KEY,
        "LAWD_CD": lawd_cd,
        "DEAL_YMD": deal_ymd,
        "numOfRows": "1000",
        "pageNo": "1",
    }
    async with httpx.AsyncClient(timeout=15) as hclient:
        res = await hclient.get(APT_TRADE_URL, params=params)

    try:
        root = ET.fromstring(res.text)
    except ET.ParseError:
        return []

    result = []
    for item in root.findall(".//item"):
        if item.findtext("cdealType", "").strip():  # 계약 해제 건 제외
            continue
        if item.findtext("landLeaseholdGbn", "").strip() == "Y":  # 지분거래 제외
            continue
        try:
            price = int(item.findtext("dealAmount", "0").replace(",", "").strip())
            area = float(item.findtext("excluUseAr", "0"))
            apt_nm = item.findtext("aptNm", "").strip()
            umd_nm = item.findtext("umdNm", "").strip()
        except (ValueError, AttributeError):
            continue

        if area <= 0 or price <= 0:
            continue

        pyeong = area / 3.3058
        result.append({
            "apt_nm": apt_nm,
            "umd_nm": umd_nm,
            "price": price,
            "area": area,
            "pyeong": round(pyeong, 1),
            "price_per_pyeong": round(price / pyeong),
        })

    return result


def normalize_apt_name(name: str) -> str:
    """아파트명 정규화: 공통 접미사 제거 후 핵심 명칭만 추출"""
    suffixes = ["아파트", "빌라", "단지", "APT", "apt", "주상복합", "오피스텔"]
    result = name.strip()
    for s in suffixes:
        if result.endswith(s):
            result = result[: -len(s)].strip()
            break
    return result


def filter_apt(items: list[dict], apt_name: str) -> list[dict]:
    """단지명 매칭 (정규화된 이름으로 부분 일치)"""
    core = normalize_apt_name(apt_name)
    return [i for i in items if core in i["apt_nm"]]


def filter_area(items: list[dict], min_p: float = 18, max_p: float = 26) -> list[dict]:
    return [i for i in items if min_p <= i["pyeong"] <= max_p]


def avg_ppp(items: list[dict]) -> float | None:
    """평균 평단가 (만원/평), 데이터 없으면 None"""
    if not items:
        return None
    return round(sum(i["price_per_pyeong"] for i in items) / len(items))


def forward_fill(lst: list[float | None]) -> list[float]:
    """None을 앞 값으로 채움. 앞에서도 None이면 뒤 값으로"""
    result: list[float | None] = list(lst)
    # forward pass
    last = None
    for i, v in enumerate(result):
        if v is not None:
            last = v
        elif last is not None:
            result[i] = last
    # backward pass (앞부분 None 처리)
    last = None
    for i in range(len(result) - 1, -1, -1):
        if result[i] is not None:
            last = result[i]
        elif last is not None:
            result[i] = last
    return [v or 0.0 for v in result]


def change_pct(data: list[float]) -> float:
    valid = [x for x in data if x]
    if len(valid) < 2:
        return 0.0
    return round((valid[-1] / valid[0] - 1) * 100, 1)


def month_label(yyyymm: str) -> str:
    return f"{yyyymm[:4]}.{yyyymm[4:]}"  # "202501" → "2025.01"


# ── 실거래 엔드포인트 ──

@app.get("/api/address-search")
async def address_search(keyword: str) -> dict:
    """주소 자동완성 — 프론트 검색창 debounce 호출용"""
    if not JUSO_CONFIRM_KEY or not keyword.strip():
        return {"results": []}

    async with httpx.AsyncClient(timeout=10) as hclient:
        res = await hclient.get(JUSO_URL, params={
            "confmKey": JUSO_CONFIRM_KEY,
            "currentPage": "1",
            "countPerPage": "10",
            "keyword": keyword,
            "resultType": "json",
        })

    try:
        jusos = res.json().get("results", {}).get("juso", []) or []
    except Exception:
        return {"results": []}

    return {
        "results": [
            {
                "roadAddr": j.get("roadAddr", ""),
                "jibunAddr": j.get("jibunAddr", ""),
                "bdNm": j.get("bdNm", ""),
                "admCd": j.get("admCd", ""),
                "entX": j.get("entX", ""),  # 건물 입구 X좌표 (UTM-K)
                "entY": j.get("entY", ""),  # 건물 입구 Y좌표 (UTM-K)
            }
            for j in jusos
            if j.get("bdNm")  # 건물명 있는 것(아파트)만
        ]
    }


@app.get("/api/market-data")
async def market_data(
    address: str,
    lawd_cd: str | None = None,
    apt_name: str | None = None,
    dong: str | None = None,
    pyeong: int | None = None,
) -> dict:
    """주소 → 단지 + 동 평균 월별 평단가 (최근 6개월)"""
    # juso API에서 직접 받은 값이 있으면 파싱 건너뜀
    if lawd_cd and apt_name:
        dong_name = dong
    else:
        lawd_cd, apt_name, dong_name = parse_address(address)
    months_ym = get_last_n_months(36)

    all_items = await asyncio.gather(*[
        fetch_month_items(lawd_cd, ym) for ym in months_ym
    ])

    complex_prices: list[float | None] = []
    dong_prices: list[float | None] = []
    volume_counts: list[int] = []
    months_display: list[str] = []

    for ym, month_items in zip(months_ym, all_items):
        months_display.append(month_label(ym))

        # 평수 필터 범위 결정
        min_p = (pyeong - 2) if pyeong else 18
        max_p = (pyeong + 2) if pyeong else 26

        # 단지 데이터: 정규화된 단지명 부분 일치 + 동 필터 + 면적 필터
        candidates = filter_apt(month_items, apt_name) if apt_name else month_items
        if dong_name:
            candidates = [i for i in candidates if i["umd_nm"] == dong_name]
        apt_items = filter_area(candidates, min_p, max_p)

        # 동 평균: 동명 필터(있으면) + 면적 필터
        dong_items = month_items
        if dong_name:
            dong_items = [i for i in dong_items if i["umd_nm"] == dong_name]
        dong_items = filter_area(dong_items, min_p, max_p)

        complex_prices.append(avg_ppp(apt_items))
        dong_prices.append(avg_ppp(dong_items))
        # 거래량: 동 전체(면적 무관) 또는 단지 건수
        if dong_name:
            vol = len([i for i in month_items if i["umd_nm"] == dong_name])
        else:
            vol = len(apt_items)
        volume_counts.append(vol)

    complex_filled = forward_fill(complex_prices)
    dong_filled = forward_fill(dong_prices)

    latest_c = complex_filled[-1]
    latest_d = dong_filled[-1]
    vs_dong = round((latest_c / latest_d - 1) * 100, 1) if latest_d else 0.0

    return {
        "apt_name": apt_name,
        "dong_name": dong_name,
        "lawd_cd": lawd_cd,
        "months": months_display,
        "complex": complex_filled,
        "dong_avg": dong_filled,
        "volume": volume_counts,
        "stats": {
            "complex_change_pct": change_pct(complex_filled),
            "dong_change_pct": change_pct(dong_filled),
            "complex_vs_dong_pct": vs_dong,
            "latest_complex": latest_c,
            "latest_dong": latest_d,
        },
    }


@app.get("/api/apt-sizes")
async def apt_sizes(lawd_cd: str, apt_name: str, dong: str | None = None) -> dict:
    """해당 아파트에서 실제 거래된 평수 목록 반환 (최근 3개월)"""
    months_ym = get_last_n_months(3)
    all_items = await asyncio.gather(*[
        fetch_month_items(lawd_cd, ym) for ym in months_ym
    ])
    sizes: set[int] = set()
    for month_items in all_items:
        candidates = filter_apt(month_items, apt_name)
        if dong:
            candidates = [i for i in candidates if i["umd_nm"] == dong]
        for item in candidates:
            sizes.add(round(item["pyeong"]))
    return {"sizes": sorted(sizes)}


@app.get("/api/dong-data")
async def dong_data(lawd_cd: str, dong_name: str, pyeong: int | None = None) -> dict:
    """특정 동의 월별 평균 평단가 (최근 36개월). pyeong 지정 시 ±2평 필터 적용."""
    months_ym = get_last_n_months(36)

    all_items = await asyncio.gather(*[
        fetch_month_items(lawd_cd, ym) for ym in months_ym
    ])

    prices: list[float | None] = []
    months_display: list[str] = []

    for ym, month_items in zip(months_ym, all_items):
        months_display.append(month_label(ym))
        min_p = (pyeong - 2) if pyeong else 18
        max_p = (pyeong + 2) if pyeong else 26
        dong_items = filter_area([
            i for i in month_items if i["umd_nm"] == dong_name
        ], min_p=min_p, max_p=max_p)
        prices.append(avg_ppp(dong_items))

    return {
        "dong_name": dong_name,
        "months": months_display,
        "data": forward_fill(prices),
    }


# ── 생활편의 헬퍼 ──

def _utm_k_to_wgs84(ent_x: float, ent_y: float) -> tuple[float, float]:
    """UTM-K (EPSG:5179) → 근사 WGS84 (lat, lon). 서울 기준 오차 < 200m."""
    lon = (ent_x - 200_000) / 88_128 + 127.0
    lat = (ent_y - 600_000) / 111_320 + 38.0
    return lat, lon


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 WGS84 좌표 간 거리 (미터)."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _count_within(coords: list[tuple[float, float]], lat: float, lon: float, radius_m: float) -> int:
    return sum(1 for plat, plon in coords if _haversine_m(lat, lon, plat, plon) <= radius_m)


def _get_subway_coords() -> list[tuple[float, float]]:
    """서울 지하철역 좌표 — 정적 JSON 파일에서 로드 (API 불필요)."""
    global _subway_coords_cache
    if _subway_coords_cache is not None:
        return _subway_coords_cache
    try:
        import json as _json
        with open(_SUBWAY_JSON, encoding="utf-8") as f:
            stations = _json.load(f)
        _subway_coords_cache = [(s["lat"], s["lon"]) for s in stations]
    except Exception:
        _subway_coords_cache = []
    return _subway_coords_cache


def _load_static_json(path: str) -> list[dict]:
    import json as _json
    try:
        with open(path, encoding="utf-8") as f:
            return _json.load(f)
    except Exception:
        return []


def _count_type_within(items: list[dict], lat: float, lon: float, type_val: str, radius_m: float) -> int:
    return sum(
        1 for item in items
        if item.get("type") == type_val
        and _haversine_m(lat, lon, item["lat"], item["lon"]) <= radius_m
    )


def _load_static_coords(path: str) -> list[tuple[float, float]]:
    """정적 JSON 파일에서 좌표 로드."""
    import json as _json
    try:
        with open(path, encoding="utf-8") as f:
            return [(s["lat"], s["lon"]) for s in _json.load(f)]
    except Exception:
        return []


@app.get("/api/nearby-amenities")
async def nearby_amenities(
    entX: str = "",
    entY: str = "",
    radius_m: float = 1000,
) -> dict:
    """
    건물 입구 좌표(UTM-K) 기준 반경 내 생활편의 카운트.
    entX·entY: JUSO address-search API 반환값 그대로.
    """
    try:
        lat, lon = _utm_k_to_wgs84(float(entX), float(entY))
    except (ValueError, TypeError):
        return {"error": "no_coords", "subway_10min": 0, "school_1km": 0,
                "secondary_school_1km": 0, "hospital_2km": 0, "park_1km": 0,
                "highway_ic_3km": 0, "crematorium_3km": 0, "waste_plant_2km": 0,
                "highvoltage_500m": 0, "industrial_1km": 0, "prison_1km": 0,
                "military_1km": 0, "emart_2km": 0, "dept_store_3km": 0}

    # 모두 정적 JSON — API 키 불필요
    subway_count           = _count_within(_get_subway_coords(),                          lat, lon, 800)       # 도보 10분=800m
    school_count           = _count_within(_load_static_coords(_SCHOOL_JSON),            lat, lon, radius_m)
    secondary_school_count = _count_within(_load_static_coords(_SECONDARY_SCHOOL_JSON),  lat, lon, radius_m)
    hospital_count         = _count_within(_load_static_coords(_HOSPITAL_JSON),          lat, lon, 2000)       # 병원은 2km
    park_count             = _count_within(_load_static_coords(_PARK_JSON),              lat, lon, radius_m)
    ic_count               = _count_within(_load_static_coords(_HIGHWAY_IC_JSON),        lat, lon, 3000)       # IC는 3km

    stores = _load_static_json(_LARGE_STORE_JSON)
    emart_count  = _count_type_within(stores, lat, lon, "이마트", 2000)   # 2km (생활마트)
    dept_count   = _count_type_within(stores, lat, lon, "백화점", 3000)   # 3km (목적 쇼핑)

    disam = _load_static_json(_DISAMENITY_JSON)
    crematorium_count  = _count_type_within(disam, lat, lon, "화장장",      3000)  # 심리적 영향 3km
    waste_count        = _count_type_within(disam, lat, lon, "쓰레기처리장", 2000)  # 냄새 2km
    highvoltage_count  = _count_type_within(disam, lat, lon, "고압시설",     500)   # 전자파·경관 500m
    industrial_count   = _count_type_within(disam, lat, lon, "공장지역",    1000)  # 소음·냄새 1km
    prison_count       = _count_type_within(disam, lat, lon, "교도소",      1000)  # 기피 1km
    military_count     = _count_type_within(disam, lat, lon, "군부대",      1000)  # 소음·개발제한 1km

    return {
        "lat": lat,
        "lon": lon,
        "radius_m": int(radius_m),
        "subway_10min":         subway_count,
        "school_1km":           school_count,
        "secondary_school_1km": secondary_school_count,
        "hospital_2km":         hospital_count,
        "park_1km":             park_count,
        "highway_ic_3km":       ic_count,
        "crematorium_3km":      crematorium_count,
        "waste_plant_2km":      waste_count,
        "highvoltage_500m":     highvoltage_count,
        "industrial_1km":       industrial_count,
        "prison_1km":           prison_count,
        "military_1km":         military_count,
        "emart_2km":            emart_count,
        "dept_store_3km":       dept_count,
    }


# ── 챗봇 헬퍼 ──

def build_context_str(ctx: ChartContext) -> str:
    months_str = ", ".join(ctx.months) if ctx.months else "최근 6개월"
    lines = [
        f"매물: {ctx.address} ({ctx.size_pyeong}평)",
        f"분석 기간: {months_str}",
        f"단지 평단가 추이: {ctx.complex} (만원/평)",
        f"동 평균 평단가: {ctx.dong} (만원/평)",
    ]
    if ctx.stats:
        s = ctx.stats
        lines += [
            f"단지 6개월 변화율: {s.complex_change_pct:+.1f}%",
            f"동 평균 변화율: {s.dong_change_pct:+.1f}%",
            f"단지 vs 동 평균: {s.complex_vs_dong_pct:+.1f}%",
            f"최신 단지 평단가: {s.latest_complex:,.0f}만원/평",
            f"최신 동 평균: {s.latest_dong:,.0f}만원/평",
        ]
    for d in ctx.active_dongs:
        pct = round((d.data[-1] / d.data[0] - 1) * 100, 1) if d.data and d.data[0] else 0
        lines.append(f"{d.name} 평단가: {d.data} / 6개월 변화: {pct:+.1f}%")
    return "\n".join(lines)


# ── 챗봇 엔드포인트 ──

SYSTEM_PROMPT_TEMPLATE = """\
당신은 VerifyHome의 시세 분석 AI입니다.
사용자가 매입을 고려 중인 아파트의 실거래가 차트 데이터와 입지 정보를 분석해 궁금증에 답합니다.

## 역할
- 차트 데이터를 쉽게 해석해 주는 동네 부동산 전문가처럼 말합니다.
- "데이터를 보면 ~" 식으로 근거를 명시합니다.

## 현재 분석 대상 (이 수치만 사용)
{context_str}

## 답변 규칙
1. **할루시네이션 금지**: 위 데이터에 없는 수치는 절대 인용하지 않습니다.
2. **수치 근거 필수**: 모든 판단에 위 데이터의 숫자를 근거로 붙입니다.
3. **최대 5문장**: 간결하게.
4. **투자 권유 금지**: "사세요/파세요" 금지. "데이터상으로는 ~로 보입니다" 수준까지만.
5. **비교 동이 추가된 경우**: 추가된 동 데이터를 적극 활용해 비교 분석합니다.
6. **추세 예측 금지**: 과거·현재 데이터만 서술, 미래 전망은 하지 않습니다.
7. **이유·원인 질문** ("왜", "이유가", "원인이"): 입지 분석 데이터가 제공된 경우 아래 항목별로 근거를 활용합니다. 없으면 "추이만 말씀드리면 ~" 형식으로 피봇합니다.
8. **교통 접근성**: 지하철역(도보 10분 내) N개, 고속도로IC(3km 내) N개는 교통 프리미엄의 상관관계 근거로 씁니다.
9. **교육 환경(학군)**: 초등학교 수와 중고등학교 수가 많을수록 학군 프리미엄과 연관될 수 있습니다. 특히 중고등학교가 여럿이면 "학군 수요가 있는 지역"으로 언급할 수 있습니다.
10. **의료·생활 편의**: 병원(2km 내), 이마트(2km 내), 백화점/복합몰(3km 내) 수를 생활 인프라 프리미엄 근거로 활용합니다.
11. **혐오시설(시세 할인 요인)**: 입지 분석에 "혐오시설" 항목이 있으면 시세가 상대적으로 낮은 원인 중 하나로 언급할 수 있습니다. 화장장·쓰레기처리장은 심리적 기피, 고압시설은 전자기파 우려, 공장지역은 소음·매연, 교도소·군부대는 이미지 요인으로 표현합니다. 인과관계가 아닌 "관련이 있을 수 있습니다" 수준으로만 표현합니다.
12. **상관관계 표현**: "때문에" 대신 "와 관련이 있을 수 있습니다", "영향을 줄 수 있는 요인입니다" 수준으로 표현합니다.
13. **한국어**로 답합니다.
"""


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    context_str = build_context_str(req.context)
    if req.amenity_summary:
        context_str += f"\n\n## 입지 분석\n{req.amenity_summary}"
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(context_str=context_str)

    messages: list[dict[str, Any]] = []
    for h in req.history[-10:]:
        if h.role in ("user", "assistant"):
            messages.append({"role": h.role, "content": h.content})
    messages.append({"role": "user", "content": req.message})

    response = await client.messages.create(
        model=os.environ.get("LLM_MODEL", "claude-sonnet-4-6"),
        max_tokens=512,
        system=system_prompt,
        messages=messages,
    )
    reply = response.content[0].text if response.content else "잠시 후 다시 시도해주세요."
    return ChatResponse(reply=reply)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
