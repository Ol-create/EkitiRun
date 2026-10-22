"""Pydantic request/response models for scans."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ScanIn(BaseModel):
    client_id: uuid.UUID = Field(description="Generated on the phone; retries reuse it")
    qr_token: str = Field(
        max_length=128, description="The QR's contents, or the typed bib for a manual entry"
    )
    scanned_at: datetime = Field(description="The phone's clock")
    entry: Literal["qr", "manual"] = "qr"


class ScanBatchIn(BaseModel):
    device_id: str = Field(min_length=1, max_length=64)
    checkpoint_id: int
    scans: list[ScanIn] = Field(max_length=500)


class ScanResult(BaseModel):
    client_id: uuid.UUID
    status: Literal["accepted", "duplicate", "invalid"]
    bib_number: str | None = None


class ScanBatchOut(BaseModel):
    results: list[ScanResult]
