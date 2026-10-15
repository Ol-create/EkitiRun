"""Checkpoint model. Owner: Lead (E2)."""

from decimal import Decimal

from sqlalchemy import Boolean, Float, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Checkpoint(Base):
    __tablename__ = "checkpoints"
    __table_args__ = (UniqueConstraint("route_id", "code", name="uq_checkpoints_route_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id"))
    code: Mapped[str] = mapped_column(String(16))  # START, CP5, FINISH
    name: Mapped[str] = mapped_column(String(80))
    distance_km: Mapped[Decimal] = mapped_column(Numeric(7, 4))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    is_start: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_finish: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Volunteers unlock the scanner for this checkpoint with a PIN (E7).
    pin_hash: Mapped[str | None] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
