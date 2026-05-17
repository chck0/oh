"""
Pydantic 스키마 — 요청/응답 데이터 모델
"""
from pydantic import BaseModel, Field
from typing import Optional


class SearchRequest(BaseModel):
    workplace_address: str = Field(..., description="직장 주소 (도로명)")
    max_minutes: int = Field(60, ge=10, le=120, description="최대 통근 시간(분)")
    max_price: int = Field(50000, description="최대 가격(만원)")
    pyeong_types: list[str] = Field(default_factory=lambda: ['20평대'])


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
