"""장소 매칭 모듈 테스트."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.place_matcher import find_nearest_place, _haversine


def test_haversine():
    """하버사인 거리 계산 테스트."""
    # 서울역 → 시청역 (약 1km)
    dist = _haversine(37.5547, 126.9707, 37.5662, 126.9779)
    assert 1000 < dist < 1500, f"Expected ~1300m, got {dist:.1f}m"
    print(f"PASS: 하버사인 거리 = {dist:.1f}m")


def test_find_nearest():
    """가장 가까운 장소 찾기 테스트."""
    result = find_nearest_place(37.5891, 127.0234)
    assert result is not None, "Expected a match"
    assert result["name"] == "홍릉 정자각"
    print(f"PASS: 매칭 장소 = {result['name']} ({result['distance_m']}m)")


def test_too_far():
    """500m 초과 시 None 반환 테스트."""
    result = find_nearest_place(37.0, 127.0)
    assert result is None, f"Expected None, got {result}"
    print("PASS: 500m 초과 → None 반환")


if __name__ == "__main__":
    test_haversine()
    test_find_nearest()
    test_too_far()
