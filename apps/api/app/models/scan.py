"""Checkpoint scan model. Owner: Lead (E2, used by E8 and E9).

- `client_id` is generated on the scanner phone, so a retried upload never
  creates a duplicate.
- One scan per runner per checkpoint. When a runner is scanned twice, E8 keeps
  the earliest `scanned_at`.
- `scanned_at` is the phone's clock; `received_at` is the server's, so clock
  drift can be detected (E8).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPk


class Scan(UUIDPk, Base):
    __tablename__ = "scans"
    __table_args__ = (
        UniqueConstraint("runner_id", "checkpoint_id", name="uq_scans_runner_checkpoint"),
    )

    client_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    runner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runners.id"))
    checkpoint_id: Mapped[int] = mapped_column(ForeignKey("checkpoints.id"), index=True)
    device_id: Mapped[str] = mapped_column(String(64))
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
