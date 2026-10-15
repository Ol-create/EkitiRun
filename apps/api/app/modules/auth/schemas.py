"""Pydantic request/response models for auth."""

from pydantic import BaseModel, Field

from app.core.schemas import NigerianPhone


class OtpRequestIn(BaseModel):
    phone: NigerianPhone


class OtpVerifyIn(BaseModel):
    phone: NigerianPhone
    code: str = Field(pattern=r"^\d{6}$", examples=["123456"])


class OtpVerifyOut(BaseModel):
    verification_token: str = Field(description="Send this to POST /registrations. Valid 30 min.")
