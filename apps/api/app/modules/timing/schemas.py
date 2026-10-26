"""Pydantic request/response models for race-office timing controls."""

from datetime import datetime

from pydantic import BaseModel, Field


class GunStartIn(BaseModel):
    at: datetime | None = Field(
        default=None, description="When the gun went. Leave empty for 'now' (tap at the gun)."
    )


class GunStartOut(BaseModel):
    category_id: int
    category_code: str
    gun_start_at: datetime


class RunnerStatusOut(BaseModel):
    bib_number: str
    status: str
