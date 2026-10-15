"""Pydantic request/response models for GPS tracking."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.schemas import LivePosition


class GpsPositionIn(BaseModel):
    device_id: str = Field(min_length=1, max_length=64)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    accuracy_m: float | None = Field(default=None, ge=0)
    battery_pct: int | None = Field(default=None, ge=0, le=100)
    recorded_at: datetime


class GpsBatchIn(BaseModel):
    positions: list[GpsPositionIn] = Field(max_length=5000)


class GpsBatchAccepted(BaseModel):
    accepted: int


class RunnerPosition(BaseModel):
    bib_number: str
    category_code: str
    gender: Literal["M", "F"]
    lat: float
    lng: float
    distance_km: float
    is_stale: bool


class PositionsSnapshot(BaseModel):
    updated_at: datetime
    runners: list[RunnerPosition]


class PositionEvent(LivePosition):
    """Data of an `event: position` message on /stream/positions."""

    bib_number: str
