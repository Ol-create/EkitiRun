"""GPS tracker and GPS position models. Owner: Lead (E13).

- A tracker is handed to a runner at kit collection (E15) and returned at the
  finish. `runner_id` is set while it's out; one tracker per runner at a time.
- Only points from assigned trackers are stored. Points more than 200 m from the
  runner's course are kept (`off_route`) but never shown on the maps.
- Location history is deleted 30 days after the race (daily ARQ job).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt

TRACKER_STATUSES = ("available", "assigned", "returned", "lost")


class Tracker(CreatedAt, Base):
    __tablename__ = "trackers"
    __table_args__ = (
        CheckConstraint(f"status IN {TRACKER_STATUSES}", name="status_valid"),
        CheckConstraint(
            "(status = 'assigned') = (runner_id IS NOT NULL)", name="assigned_has_runner"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(String(64), unique=True)  # IMEI / Traccar unique id
    label: Mapped[str] = mapped_column(String(20), unique=True)  # printed on the unit: TRK-0001
    status: Mapped[str] = mapped_column(String(16), default="available", server_default="available")
    runner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("runners.id"), unique=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    battery_pct: Mapped[int | None] = mapped_column(Integer)


class GpsPosition(Base):
    __tablename__ = "gps_positions"
    __table_args__ = (
        Index("ix_gps_positions_runner_recorded", "runner_id", "recorded_at"),
        Index("ix_gps_positions_recorded_at", "recorded_at"),  # for the 30-day clean-up
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tracker_id: Mapped[int] = mapped_column(ForeignKey("trackers.id"))
    runner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runners.id"))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    accuracy_m: Mapped[float | None] = mapped_column(Float)
    battery_pct: Mapped[int | None] = mapped_column(Integer)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # tracker's GPS time
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Where the point falls along the runner's course, and whether it is too far from it.
    route_distance_km: Mapped[float | None] = mapped_column(Float)
    off_route_m: Mapped[float | None] = mapped_column(Float)
    off_route: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
