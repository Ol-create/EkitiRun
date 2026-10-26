"""Pydantic request/response models for admin login."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class AdminLoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class AdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str


class AdminLoginOut(BaseModel):
    token: str = Field(description="Send as `Authorization: Bearer <token>` to /admin endpoints")
    expires_at: datetime
    admin: AdminOut
