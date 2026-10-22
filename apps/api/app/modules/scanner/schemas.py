"""Pydantic request/response models for checkpoint scanners."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ScannerLoginIn(BaseModel):
    pin: str = Field(pattern=r"^\d{6}$", examples=["482913"])
    device_id: str = Field(
        min_length=8, max_length=64, description="Random id the phone generates once and keeps"
    )


class CheckpointInfo(BaseModel):
    id: int
    code: str
    name: str
    distance_km: float
    is_start: bool
    is_finish: bool
    category_codes: list[str] = Field(description="Categories whose course has this checkpoint")


class ScannerLoginOut(BaseModel):
    token: str = Field(description="Send as `Authorization: Bearer <token>`")
    expires_at: datetime
    checkpoint: CheckpointInfo


class RosterRunner(BaseModel):
    runner_id: uuid.UUID
    bib_number: str
    full_name: str
    category_code: str


class RosterOut(BaseModel):
    checkpoint_id: int
    generated_at: datetime
    runners: list[RosterRunner]


class ScannerDeviceOut(BaseModel):
    device_id: str
    checkpoint_id: int
    checkpoint_name: str
    category_codes: list[str]
    first_seen_at: datetime
    last_seen_at: datetime
    scans_uploaded: int
    clock_offset_s: float | None = Field(
        description="Server time minus the phone's time at its last upload, in seconds"
    )
    clock_flagged: bool = Field(description="True when the clock is off by more than 2 minutes")
