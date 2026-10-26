
"""Pydantic schemas for sponsor tier requests and responses."""

from pydantic import BaseModel, ConfigDict, Field


class SponsorTierBase(BaseModel):
    """Fields shared by sponsor tier creation and responses."""

    name: str = Field(min_length=1, max_length=100)
    amount_kobo: int = Field(gt=0)
    benefits: list[str] = Field(min_length=1)
    sort_order: int = Field(default=0, ge=0)


class SponsorTierCreate(SponsorTierBase):
    """Data required to create a sponsor tier."""

    pass


class SponsorTierUpdate(BaseModel):
    """Fields that can be updated on a sponsor tier."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    amount_kobo: int | None = Field(default=None, gt=0)
    benefits: list[str] | None = Field(default=None, min_length=1)
    sort_order: int | None = Field(default=None, ge=0)


class SponsorTierResponse(SponsorTierBase):
    """Sponsor tier data returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int

