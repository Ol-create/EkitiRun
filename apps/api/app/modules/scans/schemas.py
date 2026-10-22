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
    sent_at: datetime | None = Field(
        default=None,
        description="The phone's clock when uploading. Lets the server measure clock drift.",
    )


InvalidReason = Literal["bad_qr", "unknown_bib", "wrong_course"]


class ScanResult(BaseModel):
    client_id: uuid.UUID
    status: Literal["accepted", "duplicate", "invalid"] = Field(
        description="accepted: saved (or replaced a later scan of the same runner here). "
        "duplicate: already saved, nothing to do. invalid: see `reason`."
    )
    bib_number: str | None = None
    reason: InvalidReason | None = Field(
        default=None,
        description="Only for invalid: bad_qr (forged or damaged code), unknown_bib, "
        "wrong_course (the runner's race doesn't pass this checkpoint)",
    )


class ScanBatchOut(BaseModel):
    results: list[ScanResult]
