"""
카카오 로컬 API를 사용해 특정 좌표 반경 내 POI를 수집합니다.
https://developers.kakao.com/docs/latest/ko/local/dev-guide
"""

import os
import httpx
from dotenv import load_dotenv

load_dotenv()

KAKAO_API_KEY = os.getenv("KAKAO_API_KEY", "")
BASE_URL = "https://dapi.kakao.com/v2/local/search/category.json"

# 카카오 카테고리 코드
CATEGORY_CODES = {
    "convenience_store": "CS2",  # 편의점
    "mart":              "MT1",  # 대형마트
    "hospital":          "HP8",  # 병원
    "pharmacy":          "PM9",  # 약국
    "school":            "SC4",  # 학교
    "subway":            "SW8",  # 지하철역
    "park":              "PK6",  # 주차장 (공원 카테고리 없음 → 별도 처리)
    "cafe":              "CE7",  # 카페
    "restaurant":        "FD6",  # 음식점
}


def fetch_poi(lat: float, lng: float, category_code: str, radius: int = 500) -> list[dict]:
    """반경 내 POI 목록을 반환합니다. 실패 시 빈 리스트."""
    if not KAKAO_API_KEY:
        raise EnvironmentError("KAKAO_API_KEY가 설정되지 않았습니다.")

    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    params = {
        "category_group_code": category_code,
        "x": lng,
        "y": lat,
        "radius": radius,
        "size": 15,
    }

    with httpx.Client(timeout=10) as client:
        res = client.get(BASE_URL, headers=headers, params=params)
        res.raise_for_status()
        documents = res.json().get("documents", [])

    return [
        {
            "name":     doc["place_name"],
            "category": category_code,
            "lat":      float(doc["y"]),
            "lng":      float(doc["x"]),
            "distance": int(doc.get("distance", 0)),
        }
        for doc in documents
    ]


def fetch_all_poi(lat: float, lng: float, radius: int = 500) -> dict[str, list]:
    """모든 카테고리 POI를 수집합니다."""
    result = {}
    for name, code in CATEGORY_CODES.items():
        try:
            result[name] = fetch_poi(lat, lng, code, radius)
        except Exception as e:
            print(f"[경고] {name} 수집 실패: {e}")
            result[name] = []
    return result


if __name__ == "__main__":
    # 테스트: 강남역 좌표
    sample = fetch_all_poi(lat=37.4979, lng=127.0276)
    for category, items in sample.items():
        print(f"{category}: {len(items)}개")
