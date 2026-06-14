"""
Pydantic 스키마 — 요청/응답 데이터 모델

NOTE: SearchRequest는 app/search.py 에 정의되어 있습니다 (validator 포함).
      이 파일에는 공용 응답/중간 스키마만 둡니다.
"""
from pydantic import BaseModel, Field
from typing import Optional


class TransitStep(BaseModel):
    type: str
    time_min: Optional[int] = None
    dist_m: Optional[int] = None
    line: str = ""
    from_: str = Field("", alias="from")
    to: str = ""


class AptResult(BaseModel):
    apt_seq: str
    apt_nm: str
    umd_nm: str
    kaptdaCnt: int
    total_time_min: int
    steps: list[TransitStep]
