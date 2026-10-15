"""Pydantic request/response models for runners.

Public endpoints: never add phone, email, date of birth or emergency contact here.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.core.schemas import CategorySummary, LivePosition

RunnerStatus = Literal["registered", "started", "finished", "dnf"]


class RunnerSearchItem(BaseModel):
    bib_number: str
    full_name: str
    category_code: str


class Split(BaseModel):
    checkpoint_id: int
    checkpoint_name: str
    distance_km: float
    scanned_at: datetime
    elapsed_seconds: int


class RunnerDetail(BaseModel):
    bib_number: str
    full_name: str
    gender: Literal["M", "F"]
    category: CategorySummary
    status: RunnerStatus
    splits: list[Split]
    finish_seconds: int | None = None
    position_overall: int | None = None
    position_category: int | None = None
    live_position: LivePosition | None = None
