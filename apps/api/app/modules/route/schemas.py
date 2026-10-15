"""Pydantic request/response models for route."""

from typing import Literal

from pydantic import BaseModel, Field


class LineString(BaseModel):
    type: Literal["LineString"] = "LineString"
    coordinates: list[list[float]] = Field(description="[lng, lat] pairs, GeoJSON order")


class CheckpointOut(BaseModel):
    id: int
    name: str
    distance_km: float
    lat: float
    lng: float


class RouteOut(BaseModel):
    category_code: str
    length_km: float
    route: LineString
    checkpoints: list[CheckpointOut]
