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


def find_place_by_name(name, csv_path=None):
    """장소 이름(부분 일치)으로 등록된 장소를 찾는다.

    Manifest #1 'Data Integrity' 구현용: 인식된 place_name이 로컬 발굴 자료와
    매칭되는지 확인하고, 있으면 data_file 경로까지 반환한다.

    Args:
        name: Gemini가 인식한 장소 이름 (예: "홍릉 정자각")
        csv_path: places.csv 경로

    Returns:
        매칭된 장소 dict (data_file 포함) 또는 None
    """
    if not name:
        return None
    places = load_places(csv_path)
    normalized = name.strip().replace(" ", "")
    for place in places:
        place_normalized = place["name"].replace(" ", "")
        if normalized == place_normalized or normalized in place_normalized or place_normalized in normalized:
            return place
    return None


def load_reference_text(data_file):
    """place dict의 data_file에 해당하는 참고 자료 텍스트를 읽는다.

    Returns:
        파일 내용 문자열, 또는 파일이 없으면 None
    """
    if not data_file:
        return None
    path = os.path.join(DATA_DIR, data_file)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return None


def list_known_place_names(csv_path=None):
    """places.csv에 등록된 모든 장소 이름 목록 (드롭다운 폴백용)."""
    try:
        places = load_places(csv_path)
        return [p["name"] for p in places]
    except Exception:
        return []
