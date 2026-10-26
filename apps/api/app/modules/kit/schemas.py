"""Pydantic request/response models for kit collection and tracker returns."""

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator


class KitLoginIn(BaseModel):
    pin: str = Field(pattern=r"^\d{6}$")
    device_id: str = Field(min_length=8, max_length=64)


class KitLoginOut(BaseModel):
    token: str = Field(description="Send as `Authorization: Bearer <token>`")
    expires_at: datetime


class KitAssignIn(BaseModel):
    qr_token: str | None = Field(default=None, description="Scanned from the runner's QR code")
    bib_number: str | None = Field(
        default=None, description="Typed bib, only when the QR won't scan (check the runner's ID)"
    )
    tracker_label: str = Field(
        min_length=1,
        max_length=64,
        description="Tracker label (TRK-0031, or just 31) or the device number on its barcode",
        examples=["TRK-0031"],
    )

    @model_validator(mode="after")
    def one_runner(self) -> Self:
        if (self.qr_token is None) == (self.bib_number is None):
            raise ValueError("Send exactly one of qr_token or bib_number")
        return self


class KitAssignOut(BaseModel):
    bib_number: str
    full_name: str
    category_code: str
    tracker_label: str
    already_assigned: bool = Field(
        default=False, description="True if this exact pair was already linked (a repeat scan)"
    )


class KitReturnIn(BaseModel):
    tracker_label: str = Field(min_length=1, max_length=64, examples=["TRK-0031"])


class KitReturnOut(BaseModel):
    bib_number: str
    full_name: str
    tracker_label: str


class OutstandingTracker(BaseModel):
    tracker_label: str
    bib_number: str
    full_name: str
    category_code: str
    race_status: Literal["registered", "started", "finished", "dnf"]
    assigned_at: datetime | None


class OutstandingOut(BaseModel):
    out: int = Field(description="Trackers handed out and not returned yet")
    trackers: list[OutstandingTracker]
