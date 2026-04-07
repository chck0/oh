"""Step 2: GPS 좌표를 등록된 장소와 매칭하는 모듈."""

import csv
import math
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
PLACES_CSV = os.path.join(DATA_DIR, "places.csv")
MAX_DISTANCE_M = 500


def _haversine(lat1, lng1, lat2, lng2):
    """하버사인 공식으로 두 좌표 간 거리(미터)를 계산한다."""
    R = 6371000  # 지구 반지름 (미터)
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def load_places(csv_path=None):
    """places.csv에서 장소 목록을 로드한다."""
    if csv_path is None:
        csv_path = PLACES_CSV
    places = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            places.append(
                {
                    "name": row["name"],
                    "lat": float(row["lat"]),
                    "lng": float(row["lng"]),
                    "data_file": row["data_file"],
                    "category": row["category"],
                }
            )
    return places


def find_nearest_place(lat, lng, csv_path=None):
    """주어진 좌표에서 가장 가까운 장소를 찾는다.

    Args:
        lat: 위도
        lng: 경도
        csv_path: places.csv 경로 (기본값: data/places.csv)

    Returns:
        가장 가까운 장소 dict (distance_m 포함) 또는 500m 초과 시 None
    """
    places = load_places(csv_path)
    if not places:
        return None

    nearest = None
    min_dist = float("inf")

    for place in places:
        dist = _haversine(lat, lng, place["lat"], place["lng"])
        if dist < min_dist:
            min_dist = dist
            nearest = place

    if min_dist > MAX_DISTANCE_M:
        return None

    result = dict(nearest)
    result["distance_m"] = round(min_dist, 1)
    return result
