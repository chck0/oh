"""Step 1: 사진 EXIF에서 GPS 좌표를 추출하는 모듈."""

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS


def _dms_to_decimal(dms, ref):
    """도/분/초(DMS)를 십진수(Decimal Degrees)로 변환한다."""
    degrees = float(dms[0])
    minutes = float(dms[1])
    seconds = float(dms[2])
    decimal = degrees + minutes / 60.0 + seconds / 3600.0
    if ref in ("S", "W"):
        decimal = -decimal
    return decimal


def extract_gps(image):
    """PIL Image 또는 파일 경로에서 GPS 좌표를 추출한다.

    Args:
        image: PIL Image 객체 또는 파일 경로 문자열

    Returns:
        {"lat": float, "lng": float} 또는 GPS 정보가 없으면 None
    """
    if isinstance(image, str):
        image = Image.open(image)

    try:
        exif_data = image._getexif()
    except (AttributeError, Exception):
        return None

    if exif_data is None:
        return None

    gps_info = {}
    for tag_id, value in exif_data.items():
        tag_name = TAGS.get(tag_id, tag_id)
        if tag_name == "GPSInfo":
            for gps_tag_id, gps_value in value.items():
                gps_tag_name = GPSTAGS.get(gps_tag_id, gps_tag_id)
                gps_info[gps_tag_name] = gps_value

    if not gps_info:
        return None

    try:
        lat = _dms_to_decimal(
            gps_info["GPSLatitude"], gps_info["GPSLatitudeRef"]
        )
        lng = _dms_to_decimal(
            gps_info["GPSLongitude"], gps_info["GPSLongitudeRef"]
        )
        return {"lat": lat, "lng": lng}
    except (KeyError, TypeError, IndexError):
        return None
