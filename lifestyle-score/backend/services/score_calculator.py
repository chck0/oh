"""
생활권 스코어 계산 엔진.

6개 카테고리를 점수화하여 종합 스코어를 반환합니다.
카테고리: 교통, 편의시설, 교육, 환경, 치안, 인프라
"""

CATEGORY_WEIGHTS = {
    "transit":      0.25,
    "convenience":  0.20,
    "education":    0.20,
    "environment":  0.15,
    "safety":       0.15,
    "infra":        0.05,
}


def distance_score(distance_m: float) -> float:
    """거리(m) 기반 감쇠 점수. 가까울수록 높음."""
    if distance_m <= 100:
        return 100.0
    elif distance_m <= 300:
        return 80.0
    elif distance_m <= 500:
        return 60.0
    elif distance_m <= 1000:
        return 40.0
    return 0.0


def calculate_score(lat: float, lng: float, weights: dict | None = None) -> dict:
    """
    주어진 좌표의 생활권 스코어를 계산합니다.
    weights를 전달하면 사용자 맞춤 가중치를 적용합니다.
    실제 POI 연동 전 더미 데이터로 구조를 검증합니다.
    """
    applied_weights = weights or CATEGORY_WEIGHTS

    # TODO: 실제 DB/API 조회로 교체 (Phase 2)
    raw_scores = {
        "transit":     75.0,
        "convenience": 82.0,
        "education":   68.0,
        "environment": 55.0,
        "safety":      79.0,
        "infra":       70.0,
    }

    total = sum(
        raw_scores[cat] * applied_weights.get(cat, 0)
        for cat in raw_scores
    )

    return {
        "lat": lat,
        "lng": lng,
        "total_score": round(total, 1),
        "categories": raw_scores,
        "weights": applied_weights,
    }
