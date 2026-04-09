"""GPS 추출 모듈 테스트."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image
from modules.gps_extractor import extract_gps


def test_no_gps_image():
    """GPS 정보가 없는 이미지에서 None을 반환하는지 확인."""
    img = Image.new("RGB", (100, 100), color="red")
    result = extract_gps(img)
    assert result is None, f"Expected None, got {result}"
    print("PASS: GPS 없는 이미지 → None 반환")


def test_gps_from_file():
    """테스트 사진 파일에서 GPS를 추출 (파일이 있을 경우만)."""
    test_jpg = os.path.join(os.path.dirname(__file__), "test_sample.jpg")
    if not os.path.exists(test_jpg):
        print("SKIP: test_sample.jpg 없음")
        return
    result = extract_gps(test_jpg)
    if result:
        print(f"PASS: GPS 추출 성공 → lat={result['lat']:.6f}, lng={result['lng']:.6f}")
    else:
        print("INFO: test_sample.jpg에 GPS 정보 없음")


if __name__ == "__main__":
    test_no_gps_image()
    test_gps_from_file()
