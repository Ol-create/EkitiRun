"""Pydantic request/response models for categories.

Response models describe exactly what the API returns (see docs/api-contract.md).
`from_attributes=True` lets them be built straight from SQLAlchemy objects.
"""

from pydantic import BaseModel, ConfigDict


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    distance_km: float
    cap: int
    slots_left: int
    is_full: bool
