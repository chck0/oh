"""국토교통부 실거래가 API 클라이언트 + 샘플 데이터 fallback.

공공데이터포털(data.go.kr) 오피스텔 매매/전월세 실거래 조회 API를 호출하고,
XML 응답을 파싱하여 에이전트 컨텍스트용 텍스트 블록으로 변환한다.

API 키가 없거나 호출 실패 시, Gold Standard 기반 샘플 데이터를 반환하여
데모/테스트가 API 없이도 작동한다.
"""
from __future__ import annotations

import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

REGION_CODES: dict[str, str] = {
    # ── 서울특별시 (25개구) ──
    "종로구": "11110",
    "중구": "11140",
    "용산구": "11170",
    "성동구": "11200",
    "광진구": "11215",
    "동대문구": "11230",
    "중랑구": "11260",
    "성북구": "11290",
    "강북구": "11305",
    "도봉구": "11320",
    "노원구": "11350",
    "은평구": "11380",
    "서대문구": "11410",
    "마포구": "11440",
    "양천구": "11470",
    "강서구": "11500",
    "구로구": "11530",
    "금천구": "11545",
    "영등포구": "11560",
    "동작구": "11590",
    "관악구": "11620",
    "서초구": "11650",
    "강남구": "11680",
    "송파구": "11710",
    "강동구": "11740",
    # ── 경기도 (주요 시/구) ──
    "수원시 장안구": "41111",
    "수원시 권선구": "41113",
    "수원시 팔달구": "41115",
    "수원시 영통구": "41117",
    "성남시 수정구": "41131",
    "성남시 중원구": "41133",
    "성남시 분당구": "41135",
    "안양시 만안구": "41171",
    "안양시 동안구": "41173",
    "부천시": "41190",
    "광명시": "41210",
    "평택시": "41220",
    "안산시 상록구": "41271",
    "안산시 단원구": "41273",
    "고양시 덕양구": "41281",
    "고양시 일산동구": "41285",
    "고양시 일산서구": "41287",
    "과천시": "41290",
    "구리시": "41310",
    "남양주시": "41360",
    "시흥시": "41390",
    "군포시": "41410",
    "의왕시": "41430",
    "하남시": "41450",
    "용인시 처인구": "41461",
    "용인시 기흥구": "41463",
    "용인시 수지구": "41465",
    "파주시": "41480",
    "김포시": "41570",
    "화성시": "41590",
    "광주시": "41610",
    "양주시": "41630",
    # ── 부산광역시 (주요 구) ──
    "부산 해운대구": "26350",
    "부산 수영구": "26500",
    "부산 부산진구": "26230",
    "부산 동래구": "26260",
    "부산 남구": "26290",
    "부산 연제구": "26470",
    "부산 사하구": "26380",
    # ── 대구광역시 (주요 구) ──
    "대구 수성구": "27260",
    "대구 달서구": "27290",
    "대구 중구": "27110",
    "대구 북구": "27230",
    # ── 인천광역시 (주요 구) ──
    "인천 연수구": "28185",
    "인천 남동구": "28200",
    "인천 부평구": "28237",
    "인천 서구": "28260",
    "인천 미추홀구": "28177",
    # ── 광주광역시 (주요 구) ──
    "광주 서구": "29140",
    "광주 북구": "29170",
    "광주 광산구": "29200",
    # ── 대전광역시 (주요 구) ──
    "대전 유성구": "30200",
    "대전 서구": "30170",
    "대전 중구": "30140",
}

REGION_GROUPS: dict[str, list[str]] = {
    "서울": [k for k in REGION_CODES if REGION_CODES[k].startswith("11")],
    "경기": [k for k in REGION_CODES if REGION_CODES[k].startswith("41")],
    "부산": [k for k in REGION_CODES if REGION_CODES[k].startswith("26")],
    "대구": [k for k in REGION_CODES if REGION_CODES[k].startswith("27")],
    "인천": [k for k in REGION_CODES if REGION_CODES[k].startswith("28")],
    "광주": [k for k in REGION_CODES if REGION_CODES[k].startswith("29")],
    "대전": [k for k in REGION_CODES if REGION_CODES[k].startswith("30")],
}

OFFI_TRADE_URL = "https://openapi.molit.go.kr/OpenAPI_ToolInstall498/service/rest/RTMSOBJSvc/getRTMSDataSvcOffiTrade"
OFFI_RENT_URL = "https://openapi.molit.go.kr/OpenAPI_ToolInstallPack498/service/rest/RTMSOBJSvc/getRTMSDataSvcOffiRent"
APT_TRADE_URL = "https://openapi.molit.go.kr:8081/OpenAPI_ToolInstall498/service/rest/RTMSOBJSvc/getRTMSDataSvcAptTrade"
APT_RENT_URL = "https://openapi.molit.go.kr:8081/OpenAPI_ToolInstallPack498/service/rest/RTMSOBJSvc/getRTMSDataSvcAptRent"

# backward compat aliases
TRADE_API_URL = OFFI_TRADE_URL
RENT_API_URL = OFFI_RENT_URL

PROPERTY_TYPES = ("officetel", "apartment")
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # seconds


@dataclass
class TradeRecord:
    district: str       # 법정동
    name: str           # 단지명
    area: float         # 전용면적 (㎡)
    floor: int          # 층
    price: int          # 거래금액 (만원)
    year: int           # 년
    month: int          # 월
    day: int            # 일

    @property
    def price_billion(self) -> str:
        if self.price >= 10000:
            b = self.price // 10000
            r = self.price % 10000
            return f"{b}억 {r:,}만원" if r else f"{b}억"
        return f"{self.price:,}만원"


@dataclass
class RentRecord:
    district: str
    name: str
    area: float
    floor: int
    deposit: int        # 보증금 (만원)
    monthly_rent: int   # 월세 (만원)
    year: int
    month: int
    day: int

    @property
    def rent_display(self) -> str:
        dep = f"{self.deposit:,}"
        return f"보증금 {dep}만원 / 월세 {self.monthly_rent:,}만원"


@dataclass
class RegionSummary:
    region: str
    deal_month: str
    trade_records: list[TradeRecord] = field(default_factory=list)
    rent_records: list[RentRecord] = field(default_factory=list)
    is_sample: bool = False
    property_type: str = "officetel"

    @property
    def avg_trade_price(self) -> int:
        if not self.trade_records:
            return 0
        return sum(r.price for r in self.trade_records) // len(self.trade_records)

    @property
    def avg_monthly_rent(self) -> int:
        rents = [r for r in self.rent_records if r.monthly_rent > 0]
        if not rents:
            return 0
        return sum(r.monthly_rent for r in rents) // len(rents)

    @property
    def avg_area(self) -> float:
        all_records = self.trade_records + self.rent_records
        if not all_records:
            return 0
        return sum(r.area for r in all_records) / len(all_records)


# ------------------------------------------------------------------
# API 호출 (with retry + caching)
# ------------------------------------------------------------------

_cache: dict[str, Any] = {}
_cache_ttl: dict[str, float] = {}
CACHE_SECONDS = 3600  # 1시간


def _fetch_with_retry(url: str, max_retries: int = MAX_RETRIES) -> str:
    for attempt in range(max_retries):
        try:
            with urlopen(url, timeout=10) as resp:
                return resp.read().decode("utf-8")
        except (URLError, TimeoutError):
            if attempt < max_retries - 1:
                time.sleep(RETRY_BACKOFF * (attempt + 1))
    safe_url = re.sub(r"serviceKey=[^&]+", "serviceKey=***", url)
    raise URLError(f"API 호출 {max_retries}회 재시도 실패: {safe_url}")


def _cached_fetch(cache_key: str, url: str) -> str:
    now = time.time()
    if cache_key in _cache and now - _cache_ttl.get(cache_key, 0) < CACHE_SECONDS:
        return _cache[cache_key]
    data = _fetch_with_retry(url)
    _cache[cache_key] = data
    _cache_ttl[cache_key] = now
    return data


def fetch_trades(
    region_code: str, deal_ym: str, api_key: str,
    property_type: str = "officetel",
) -> list[TradeRecord]:
    base_url = APT_TRADE_URL if property_type == "apartment" else OFFI_TRADE_URL
    params = {
        "serviceKey": api_key,
        "LAWD_CD": region_code,
        "DEAL_YMD": deal_ym,
    }
    url = f"{base_url}?{urlencode(params)}"
    cache_key = f"trade:{property_type}:{region_code}:{deal_ym}"
    xml_data = _cached_fetch(cache_key, url)
    name_tag = "아파트" if property_type == "apartment" else "단지"
    return _parse_trade_xml(xml_data, name_tag=name_tag)


def fetch_rents(
    region_code: str, deal_ym: str, api_key: str,
    property_type: str = "officetel",
) -> list[RentRecord]:
    base_url = APT_RENT_URL if property_type == "apartment" else OFFI_RENT_URL
    params = {
        "serviceKey": api_key,
        "LAWD_CD": region_code,
        "DEAL_YMD": deal_ym,
    }
    url = f"{base_url}?{urlencode(params)}"
    cache_key = f"rent:{property_type}:{region_code}:{deal_ym}"
    xml_data = _cached_fetch(cache_key, url)
    name_tag = "아파트" if property_type == "apartment" else "단지"
    return _parse_rent_xml(xml_data, name_tag=name_tag)


def _parse_trade_xml(xml_data: str, name_tag: str = "단지") -> list[TradeRecord]:
    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as e:
        logging.warning("매매 XML 파싱 실패: %s", e)
        return []
    records: list[TradeRecord] = []
    for item in root.iter("item"):
        records.append(TradeRecord(
            district=_text(item, "법정동"),
            name=_text(item, name_tag),
            area=float(_text(item, "전용면적") or "0"),
            floor=int(_text(item, "층") or "0"),
            price=int(_text(item, "거래금액", "").replace(",", "").strip() or "0"),
            year=int(_text(item, "년") or "0"),
            month=int(_text(item, "월") or "0"),
            day=int(_text(item, "일") or "0"),
        ))
    return records


def _parse_rent_xml(xml_data: str, name_tag: str = "단지") -> list[RentRecord]:
    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as e:
        logging.warning("임대 XML 파싱 실패: %s", e)
        return []
    records: list[RentRecord] = []
    for item in root.iter("item"):
        records.append(RentRecord(
            district=_text(item, "법정동"),
            name=_text(item, name_tag),
            area=float(_text(item, "전용면적") or "0"),
            floor=int(_text(item, "층") or "0"),
            deposit=int(_text(item, "보증금", "").replace(",", "").strip() or "0"),
            monthly_rent=int(_text(item, "월세금액", "").replace(",", "").strip() or "0"),
            year=int(_text(item, "년") or "0"),
            month=int(_text(item, "월") or "0"),
            day=int(_text(item, "일") or "0"),
        ))
    return records


def _text(item: ET.Element, tag: str, default: str = "") -> str:
    el = item.find(tag)
    return el.text.strip() if el is not None and el.text else default


# ------------------------------------------------------------------
# 통합 조회 (API → fallback)
# ------------------------------------------------------------------


def get_region_data(
    region_name: str,
    deal_ym: str | None = None,
    api_key: str | None = None,
    property_type: str = "officetel",
) -> RegionSummary:
    """지역 실거래 데이터 조회. API 키 없으면 샘플 데이터 반환."""
    api_key = api_key or os.getenv("DATA_GO_KR_API_KEY")
    region_code = REGION_CODES.get(region_name)

    if not deal_ym:
        from datetime import datetime
        now = datetime.now()
        if now.month <= 2:
            deal_ym = f"{now.year - 1}{now.month + 10:02d}"
        else:
            deal_ym = f"{now.year}{now.month - 2:02d}"

    if api_key and region_code:
        try:
            trades = fetch_trades(region_code, deal_ym, api_key, property_type)
            rents = fetch_rents(region_code, deal_ym, api_key, property_type)
            return RegionSummary(
                region=region_name,
                deal_month=deal_ym,
                trade_records=trades,
                rent_records=rents,
                is_sample=False,
                property_type=property_type,
            )
        except Exception as e:
            logging.warning("API 호출 실패 (%s): %s — 샘플 데이터로 대체합니다.", region_name, e)

    return _get_sample_data(region_name, deal_ym, property_type)


def get_multi_region_data(
    regions: list[str],
    deal_ym: str | None = None,
    property_type: str = "officetel",
) -> list[RegionSummary]:
    return [get_region_data(r, deal_ym, property_type=property_type) for r in regions]


# ------------------------------------------------------------------
# 에이전트 컨텍스트 포매터
# ------------------------------------------------------------------


def format_for_agents(summaries: list[RegionSummary]) -> str:
    """RegionSummary 리스트를 에이전트 주입용 텍스트 블록으로 변환."""
    if not summaries:
        return ""

    lines = ["=== 📈 부동산 실거래 데이터 ==="]
    sample_flag = any(s.is_sample for s in summaries)
    if sample_flag:
        lines.append("(⚠️ API 키 미설정 — 샘플 데이터 기반)")
    lines.append("")

    for s in summaries:
        lines.append(f"■ {s.region} (조회기간: {s.deal_month})")

        if s.trade_records:
            lines.append(f"  매매 건수: {len(s.trade_records)}건")
            avg = s.avg_trade_price
            if avg >= 10000:
                lines.append(f"  평균 매매가: {avg // 10000}억 {avg % 10000:,}만원")
            else:
                lines.append(f"  평균 매매가: {avg:,}만원")
            lines.append(f"  평균 전용면적: {s.avg_area:.1f}㎡")
            lines.append("  최근 거래:")
            for r in s.trade_records[:5]:
                lines.append(
                    f"    - {r.name} {r.area}㎡ {r.floor}층 "
                    f"→ {r.price_billion} ({r.year}.{r.month:02d}.{r.day:02d})"
                )
        else:
            lines.append("  매매 실거래: 데이터 없음")

        if s.rent_records:
            rents_with_monthly = [r for r in s.rent_records if r.monthly_rent > 0]
            lines.append(f"  전월세 건수: {len(s.rent_records)}건 (월세 {len(rents_with_monthly)}건)")
            if rents_with_monthly:
                lines.append(f"  평균 월세: {s.avg_monthly_rent:,}만원")
            lines.append("  최근 전월세:")
            for r in s.rent_records[:5]:
                lines.append(
                    f"    - {r.name} {r.area}㎡ {r.floor}층 "
                    f"→ {r.rent_display} ({r.year}.{r.month:02d}.{r.day:02d})"
                )
        else:
            lines.append("  전월세 실거래: 데이터 없음")

        lines.append("")

    lines.append("=== 실거래 데이터 끝 ===")
    return "\n".join(lines)


# ------------------------------------------------------------------
# 샘플 데이터 (API 키 없을 때 fallback — Gold Standard 기반)
# ------------------------------------------------------------------


_SAMPLE_DATA: dict[str, dict[str, Any]] = {
    "강남구": {
        "trades": [
            {"district": "역삼동", "name": "역삼 센트럴 오피스텔", "area": 42.3, "floor": 8, "price": 45000, "year": 2026, "month": 2, "day": 15},
            {"district": "역삼동", "name": "역삼 파크뷰", "area": 35.7, "floor": 5, "price": 38000, "year": 2026, "month": 2, "day": 8},
            {"district": "삼성동", "name": "삼성 오피스텔타워", "area": 48.1, "floor": 12, "price": 52000, "year": 2026, "month": 1, "day": 22},
            {"district": "논현동", "name": "논현 스퀘어", "area": 39.5, "floor": 6, "price": 41000, "year": 2026, "month": 1, "day": 10},
            {"district": "대치동", "name": "대치 센트럴", "area": 44.8, "floor": 10, "price": 47000, "year": 2026, "month": 2, "day": 3},
        ],
        "rents": [
            {"district": "역삼동", "name": "역삼 센트럴 오피스텔", "area": 42.3, "floor": 7, "deposit": 3000, "monthly_rent": 120, "year": 2026, "month": 2, "day": 18},
            {"district": "삼성동", "name": "삼성 오피스텔타워", "area": 48.1, "floor": 9, "deposit": 5000, "monthly_rent": 140, "year": 2026, "month": 2, "day": 12},
            {"district": "논현동", "name": "논현 스퀘어", "area": 39.5, "floor": 4, "deposit": 2000, "monthly_rent": 110, "year": 2026, "month": 1, "day": 25},
            {"district": "대치동", "name": "대치 센트럴", "area": 44.8, "floor": 8, "deposit": 4000, "monthly_rent": 130, "year": 2026, "month": 2, "day": 5},
            {"district": "역삼동", "name": "역삼 파크뷰", "area": 35.7, "floor": 3, "deposit": 10000, "monthly_rent": 80, "year": 2026, "month": 1, "day": 15},
        ],
    },
    "성동구": {
        "trades": [
            {"district": "성수동1가", "name": "성수 에비뉴", "area": 38.2, "floor": 7, "price": 32000, "year": 2026, "month": 2, "day": 20},
            {"district": "성수동2가", "name": "서울숲 오피스텔", "area": 41.5, "floor": 9, "price": 35000, "year": 2026, "month": 2, "day": 14},
            {"district": "성수동1가", "name": "성수 IT타워", "area": 33.8, "floor": 5, "price": 28000, "year": 2026, "month": 1, "day": 28},
            {"district": "옥수동", "name": "옥수 리버뷰", "area": 45.2, "floor": 11, "price": 38000, "year": 2026, "month": 1, "day": 18},
        ],
        "rents": [
            {"district": "성수동1가", "name": "성수 에비뉴", "area": 38.2, "floor": 6, "deposit": 2000, "monthly_rent": 120, "year": 2026, "month": 2, "day": 22},
            {"district": "성수동2가", "name": "서울숲 오피스텔", "area": 41.5, "floor": 8, "deposit": 3000, "monthly_rent": 130, "year": 2026, "month": 2, "day": 10},
            {"district": "성수동1가", "name": "성수 IT타워", "area": 33.8, "floor": 4, "deposit": 1500, "monthly_rent": 100, "year": 2026, "month": 1, "day": 30},
            {"district": "옥수동", "name": "옥수 리버뷰", "area": 45.2, "floor": 10, "deposit": 5000, "monthly_rent": 110, "year": 2026, "month": 1, "day": 20},
        ],
    },
    "강서구": {
        "trades": [
            {"district": "마곡동", "name": "마곡 엠밸리", "area": 36.4, "floor": 6, "price": 28000, "year": 2026, "month": 2, "day": 17},
            {"district": "마곡동", "name": "마곡 나루", "area": 42.0, "floor": 8, "price": 31000, "year": 2026, "month": 2, "day": 9},
            {"district": "마곡동", "name": "마곡 테크노타워", "area": 33.5, "floor": 4, "price": 25000, "year": 2026, "month": 1, "day": 23},
            {"district": "마곡동", "name": "마곡 센트럴파크", "area": 39.8, "floor": 10, "price": 30000, "year": 2026, "month": 1, "day": 12},
        ],
        "rents": [
            {"district": "마곡동", "name": "마곡 엠밸리", "area": 36.4, "floor": 5, "deposit": 1500, "monthly_rent": 100, "year": 2026, "month": 2, "day": 19},
            {"district": "마곡동", "name": "마곡 나루", "area": 42.0, "floor": 7, "deposit": 2000, "monthly_rent": 110, "year": 2026, "month": 2, "day": 11},
            {"district": "마곡동", "name": "마곡 테크노타워", "area": 33.5, "floor": 3, "deposit": 1000, "monthly_rent": 85, "year": 2026, "month": 1, "day": 25},
            {"district": "마곡동", "name": "마곡 센트럴파크", "area": 39.8, "floor": 9, "deposit": 3000, "monthly_rent": 95, "year": 2026, "month": 1, "day": 14},
        ],
    },
}


_APT_SAMPLE_DATA: dict[str, dict[str, Any]] = {
    "강남구": {
        "trades": [
            {"district": "대치동", "name": "래미안대치팰리스", "area": 84.9, "floor": 15, "price": 280000, "year": 2026, "month": 2, "day": 12},
            {"district": "도곡동", "name": "도곡렉슬", "area": 59.9, "floor": 8, "price": 195000, "year": 2026, "month": 2, "day": 5},
            {"district": "삼성동", "name": "삼성래미안", "area": 114.6, "floor": 20, "price": 350000, "year": 2026, "month": 1, "day": 28},
            {"district": "역삼동", "name": "역삼자이", "area": 76.3, "floor": 11, "price": 230000, "year": 2026, "month": 1, "day": 15},
        ],
        "rents": [
            {"district": "대치동", "name": "래미안대치팰리스", "area": 84.9, "floor": 12, "deposit": 50000, "monthly_rent": 250, "year": 2026, "month": 2, "day": 10},
            {"district": "도곡동", "name": "도곡렉슬", "area": 59.9, "floor": 6, "deposit": 30000, "monthly_rent": 180, "year": 2026, "month": 2, "day": 3},
            {"district": "삼성동", "name": "삼성래미안", "area": 114.6, "floor": 18, "deposit": 70000, "monthly_rent": 350, "year": 2026, "month": 1, "day": 22},
            {"district": "역삼동", "name": "역삼자이", "area": 76.3, "floor": 9, "deposit": 40000, "monthly_rent": 200, "year": 2026, "month": 1, "day": 10},
        ],
    },
    "성동구": {
        "trades": [
            {"district": "성수동1가", "name": "서울숲트리마제", "area": 84.5, "floor": 22, "price": 210000, "year": 2026, "month": 2, "day": 18},
            {"district": "옥수동", "name": "옥수파크힐스", "area": 59.7, "floor": 10, "price": 155000, "year": 2026, "month": 2, "day": 8},
            {"district": "행당동", "name": "한진타운", "area": 76.8, "floor": 7, "price": 128000, "year": 2026, "month": 1, "day": 20},
        ],
        "rents": [
            {"district": "성수동1가", "name": "서울숲트리마제", "area": 84.5, "floor": 20, "deposit": 45000, "monthly_rent": 230, "year": 2026, "month": 2, "day": 15},
            {"district": "옥수동", "name": "옥수파크힐스", "area": 59.7, "floor": 8, "deposit": 25000, "monthly_rent": 150, "year": 2026, "month": 2, "day": 5},
            {"district": "행당동", "name": "한진타운", "area": 76.8, "floor": 5, "deposit": 15000, "monthly_rent": 110, "year": 2026, "month": 1, "day": 18},
        ],
    },
    "강서구": {
        "trades": [
            {"district": "마곡동", "name": "마곡엠밸리7단지", "area": 84.8, "floor": 12, "price": 118000, "year": 2026, "month": 2, "day": 14},
            {"district": "마곡동", "name": "마곡힐스테이트", "area": 59.9, "floor": 8, "price": 92000, "year": 2026, "month": 2, "day": 6},
            {"district": "등촌동", "name": "등촌주공5단지", "area": 49.7, "floor": 5, "price": 72000, "year": 2026, "month": 1, "day": 25},
        ],
        "rents": [
            {"district": "마곡동", "name": "마곡엠밸리7단지", "area": 84.8, "floor": 10, "deposit": 20000, "monthly_rent": 120, "year": 2026, "month": 2, "day": 12},
            {"district": "마곡동", "name": "마곡힐스테이트", "area": 59.9, "floor": 6, "deposit": 15000, "monthly_rent": 90, "year": 2026, "month": 2, "day": 4},
            {"district": "등촌동", "name": "등촌주공5단지", "area": 49.7, "floor": 3, "deposit": 10000, "monthly_rent": 60, "year": 2026, "month": 1, "day": 22},
        ],
    },
}


def _get_sample_data(
    region_name: str, deal_ym: str, property_type: str = "officetel",
) -> RegionSummary:
    source = _APT_SAMPLE_DATA if property_type == "apartment" else _SAMPLE_DATA
    data = source.get(region_name)
    if not data:
        return RegionSummary(
            region=region_name,
            deal_month=deal_ym,
            is_sample=True,
            property_type=property_type,
        )

    trades = [TradeRecord(**r) for r in data["trades"]]
    rents = [RentRecord(**r) for r in data["rents"]]
    return RegionSummary(
        region=region_name,
        deal_month=deal_ym,
        trade_records=trades,
        rent_records=rents,
        is_sample=True,
        property_type=property_type,
    )
