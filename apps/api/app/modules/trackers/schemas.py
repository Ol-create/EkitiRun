"""Pydantic request/response models for the tracker inventory."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

TrackerStatus = Literal["available", "assigned", "returned", "lost"]


class TrackerOut(BaseModel):
    id: int
    device_id: str
    label: str
    status: TrackerStatus
    bib_number: str | None = None
    battery_pct: int | None = None
    last_seen_at: datetime | None = None


class TrackerIn(BaseModel):
    device_id: str = Field(min_length=1, max_length=64, description="IMEI or Traccar unique id")
    label: str = Field(min_length=1, max_length=20, examples=["TRK-0001"])


class TrackerPatch(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=20)
    status: TrackerStatus | None = None
