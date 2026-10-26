"""Pydantic request/response models for results."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ResultItem(BaseModel):
    position: int
    bib_number: str
    full_name: str
    gender: Literal["M", "F"]
    category_code: str
    status: Literal["started", "finished", "dnf"]
    last_checkpoint: str | None
    elapsed_seconds: int | None
    finish_seconds: int | None = None


class ResultsPage(BaseModel):
    items: list[ResultItem]
    total: int


# Redis pub/sub channel that scan ingestion (E8) publishes to and /stream/results reads.
SCANS_CHANNEL = "scans"


class ScanEvent(BaseModel):
    """Data of an `event: scan` message on /stream/results."""

    bib_number: str
    category_code: str
    checkpoint_id: int
    checkpoint_name: str
    distance_km: float
    scanned_at: datetime = Field(description="Clock-corrected scan time")
    elapsed_seconds: int | None = Field(description="Since the gun; null until it is recorded")
