"""Pydantic request/response models for race-office time corrections."""

from datetime import datetime
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, Field


class SetTimeIn(BaseModel):
    scanned_at: AwareDatetime = Field(
        description="The time the runner was at the checkpoint, with its time zone "
        "(e.g. 2027-03-06T08:41:07+01:00)"
    )
    reason: str = Field(min_length=5, max_length=500, examples=["Finish paper sheet, line 214"])


class CheckpointTime(BaseModel):
    checkpoint_id: int
    checkpoint_code: str
    checkpoint_name: str
    distance_km: float
    scanned_at: datetime | None = Field(description="Clock-corrected time, or null if missing")
    elapsed_seconds: int | None
    entry: Literal["qr", "manual", "office"] | None = Field(
        description="qr / manual: from a scanner phone; office: set by the race office"
    )
    device_id: str | None


class Correction(BaseModel):
    action: Literal["add", "correct", "remove"]
    checkpoint_id: int
    checkpoint_name: str
    previous: dict[str, Any] | None
    new: dict[str, Any] | None
    reason: str
    admin_name: str
    created_at: datetime


class RunnerTimesOut(BaseModel):
    bib_number: str
    full_name: str
    category_code: str
    status: str
    checkpoints: list[CheckpointTime]
    history: list[Correction] = Field(description="Newest first")


class ChangeOut(BaseModel):
    action: Literal["add", "correct", "remove"]
    checkpoint: CheckpointTime
