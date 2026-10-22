"""Scanner phone model. Owner: Lead (E8).

One row per phone that has uploaded scans. `clock_offset_ms` is server time
minus phone time at the last upload; phones off by more than 2 minutes are
flagged for the race office (GET /admin/scanner-devices).
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

CLOCK_TOLERANCE_MS = 120_000


class ScannerDevice(Base):
    __tablename__ = "scanner_devices"

    device_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    checkpoint_id: Mapped[int] = mapped_column(ForeignKey("checkpoints.id"))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    clock_offset_ms: Mapped[int | None] = mapped_column(Integer)
    scans_uploaded: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    @property
    def clock_flagged(self) -> bool:
        return self.clock_offset_ms is not None and abs(self.clock_offset_ms) > CLOCK_TOLERANCE_MS
