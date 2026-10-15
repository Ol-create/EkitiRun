"""Response models and field types shared by several modules. Owner: Lead."""

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, Field, StringConstraints

# Nigerian mobile number in international format, e.g. +2348031234567.
NigerianPhone = Annotated[
    str,
    StringConstraints(pattern=r"^\+234[789][01]\d{8}$"),
    Field(examples=["+2348031234567"]),
]


class ErrorResponse(BaseModel):
    detail: str
    code: str


def error_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    """Document error responses in OpenAPI, so the frontend gets their types."""
    return {code: {"model": ErrorResponse} for code in status_codes}


class CategorySummary(BaseModel):
    id: int
    code: str
    name: str


class LivePosition(BaseModel):
    lat: float
    lng: float
    distance_km: float = Field(description="Distance along the route after snapping to it")
    recorded_at: datetime
    is_stale: bool = Field(description="True when the last fix is older than 2 minutes")
