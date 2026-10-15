"""Route model. Owner: Lead (E2).

One row per course. Each category runs one route; checkpoints belong to a route.
"""

from decimal import Decimal
from typing import Any

from sqlalchemy import Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Route(Base):
    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    # GeoJSON LineString, coordinates in [lng, lat] order.
    geojson: Mapped[dict[str, Any]] = mapped_column(JSONB)
    length_km: Mapped[Decimal] = mapped_column(Numeric(7, 4))
