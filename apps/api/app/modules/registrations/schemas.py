"""Pydantic request/response models for registrations."""

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.core.schemas import CategorySummary, NigerianPhone


class RegistrationIn(BaseModel):
    verification_token: str
    first_name: str = Field(min_length=1, max_length=60)
    last_name: str = Field(min_length=1, max_length=60)
    gender: Literal["M", "F"]
    date_of_birth: date
    email: EmailStr | None = None
    category_id: int
    emergency_contact_name: str = Field(min_length=2, max_length=120)
    emergency_contact_phone: NigerianPhone
    tracking_consent: bool = Field(
        description="Must be true: every runner wears a GPS tracker during the race."
    )


class RegistrationOut(BaseModel):
    runner_id: uuid.UUID
    bib_number: str = Field(examples=["H0123"])
    category: CategorySummary
    qr_png_url: str
