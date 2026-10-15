"""Pydantic request/response models for kit collection."""

from pydantic import BaseModel, Field


class KitAssignIn(BaseModel):
    qr_token: str = Field(description="Scanned from the runner's QR code")
    tracker_label: str = Field(examples=["TRK-0031"])


class KitAssignOut(BaseModel):
    bib_number: str
    full_name: str
    tracker_label: str


class KitReturnIn(BaseModel):
    tracker_label: str


class KitReturnOut(BaseModel):
    bib_number: str
    tracker_label: str
