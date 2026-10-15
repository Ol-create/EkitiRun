"""Pydantic request/response models for sponsors. Amounts are in kobo (₦1 = 100 kobo)."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, model_validator

from app.core.schemas import NigerianPhone

MIN_CUSTOM_AMOUNT_KOBO = 1_000_000  # ₦10,000


class SponsorTierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    amount_kobo: int
    benefits: list[str]
    sort_order: int


class SponsorTierIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    amount_kobo: int = Field(gt=0)
    benefits: list[str] = Field(min_length=1, max_length=15)
    sort_order: int = 0


class SponsorTierPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=60)
    amount_kobo: int | None = Field(default=None, gt=0)
    benefits: list[str] | None = Field(default=None, min_length=1, max_length=15)
    sort_order: int | None = None


class PledgeIn(BaseModel):
    tier_id: int | None = None
    custom_amount_kobo: int | None = Field(default=None, ge=MIN_CUSTOM_AMOUNT_KOBO)
    company_name: str = Field(min_length=2, max_length=120)
    contact_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    phone: NigerianPhone
    website: HttpUrl | None = None

    @model_validator(mode="after")
    def exactly_one_amount(self) -> Self:
        if (self.tier_id is None) == (self.custom_amount_kobo is None):
            raise ValueError("Send exactly one of tier_id or custom_amount_kobo")
        return self


class PledgeCreated(BaseModel):
    reference: str
    authorization_url: str = Field(description="Send the browser here to pay on Paystack")
    invoice_pdf_url: str


class PledgeStatusOut(BaseModel):
    reference: str
    company_name: str
    amount_kobo: int
    status: Literal["pending", "paid", "failed"]
    receipt_pdf_url: str | None = None
