from fastapi import APIRouter, HTTPException
from services.score_calculator import calculate_score

router = APIRouter()


@router.get("/score")
def get_score(lat: float, lng: float):
    """
    위경도 좌표를 받아 생활권 스코어를 반환합니다.
    - lat: 위도 (예: 37.4979)
    - lng: 경도 (예: 127.0276)
    """
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        raise HTTPException(status_code=422, detail="유효하지 않은 좌표입니다.")

    result = calculate_score(lat=lat, lng=lng)
    return result
