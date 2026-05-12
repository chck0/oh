"""
생활권 스코어 계산 엔진.
PostgreSQL + PostGIS에서 실제 POI 데이터를 조회해 점수를 산출합니다.
"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

CATEGORY_WEIGHTS = {
    "transit":     0.25,
    "convenience": 0.20,
    "education":   0.20,
    "environment": 0.15,
    "safety":      0.15,
    "infra":       0.05,
}

# 카테고리별 (DB에 저장된 카카오 코드, 반경m, 만점기준 개수)
SCORING_RULES = {
    "SW8": (1000, 1),   # 지하철: 1km 내 1개 = 100점
    "CS2": (500,  5),   # 편의점: 500m 내 5개 = 100점
    "MT1": (1000, 1),   # 마트:   1km 내 1개 = 100점
    "HP8": (1000, 3),   # 병원:   1km 내 3개 = 100점
    "PM9": (500,  3),   # 약국:   500m 내 3개 = 100점
    "SC4": (1000, 1),   # 학교:   1km 내 1개 = 100점
    "PK6": (500,  2),   # 공원:   500m 내 2개 = 100점
    "CE7": (500,  5),   # 카페:   500m 내 5개 = 100점
    "FD6": (500,  10),  # 음식점: 500m 내 10개 = 100점
}


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def count_poi(cur, lat: float, lng: float, category: str, radius_m: int) -> int:
    """반경 내 특정 카테고리 POI 개수를 반환합니다."""
    cur.execute("""
        SELECT COUNT(*)
        FROM poi
        WHERE category = %s
          AND ST_DWithin(
              location::geography,
              ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
              %s
          )
    """, (category, lng, lat, radius_m))
    return cur.fetchone()[0]


def poi_to_score(count: int, max_count: int) -> float:
    """POI 개수를 0~100점으로 변환합니다."""
    return min(100.0, round(count / max_count * 100, 1))


def calc_category_scores(lat: float, lng: float) -> dict:
    """좌표 기준 카테고리별 점수를 계산합니다."""
    conn = get_conn()
    raw = {}

    with conn.cursor() as cur:
        for category, (radius, max_count) in SCORING_RULES.items():
            count = count_poi(cur, lat, lng, category, radius)
            raw[category] = poi_to_score(count, max_count)

    conn.close()

    return {
        "transit":     raw["SW8"],
        "convenience": round(sum([
            raw["CS2"],
            raw["MT1"],
            raw["PM9"],
            raw["CE7"],
            raw["FD6"],
        ]) / 5, 1),
        "education":   raw["SC4"],
        "environment": raw["PK6"],
        "safety":      70.0,  # TODO: 범죄 통계 데이터 연동 시 교체
        "infra":       70.0,  # TODO: 개발계획 데이터 연동 시 교체
    }


def calculate_score(lat: float, lng: float, weights: dict | None = None) -> dict:
    """
    주어진 좌표의 생활권 스코어를 계산합니다.
    weights를 전달하면 사용자 맞춤 가중치를 적용합니다.
    """
    applied_weights = weights or CATEGORY_WEIGHTS
    categories = calc_category_scores(lat=lat, lng=lng)

    total = sum(
        categories[cat] * applied_weights.get(cat, 0)
        for cat in categories
    )

    return {
        "lat": lat,
        "lng": lng,
        "total_score": round(total, 1),
        "categories": categories,
        "weights": applied_weights,
    }
