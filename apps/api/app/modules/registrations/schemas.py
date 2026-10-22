"""Pydantic request/response models for registrations."""

import uuid
from datetime import date
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, EmailStr, Field, StringConstraints

from app.core.schemas import CategorySummary, NigerianPhone

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]


def _plausible_birth_date(value: date) -> date:
    today = date.today()
    if value >= today:
        raise ValueError("Date of birth must be in the past")
    if value.year < today.year - 100:
        raise ValueError("Date of birth looks wrong")
    return value


class RegistrationIn(BaseModel):
    verification_token: str
    first_name: Name
    last_name: Name
    gender: Literal["M", "F"]
    date_of_birth: Annotated[date, AfterValidator(_plausible_birth_date)]
    email: EmailStr | None = None
    category_id: int
    emergency_contact_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)
    ]
    emergency_contact_phone: NigerianPhone
    tracking_consent: bool = Field(
        description="Must be true: every runner wears a GPS tracker during the race."
    )


class RegistrationOut(BaseModel):
    runner_id: uuid.UUID
    bib_number: str = Field(examples=["H0123"])
    category: CategorySummary
    qr_png_url: str
