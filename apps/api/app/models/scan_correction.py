"""Audit trail of race-office time changes. Owner: Lead (E17).

Every add, correction or removal of a scan by the race office is recorded here with
the values before and after, the reason and who made it. Rows are only ever added,
so the original scanned time is never lost.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

CORRECTION_ACTIONS = ("add", "correct", "remove")


class ScanCorrection(Base):
    __tablename__ = "scan_corrections"
    __table_args__ = (
        CheckConstraint(f"action IN {CORRECTION_ACTIONS}", name="action_valid"),
        Index("ix_scan_corrections_runner", "runner_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    runner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runners.id"))
    checkpoint_id: Mapped[int] = mapped_column(ForeignKey("checkpoints.id"))
    action: Mapped[str] = mapped_column(String(8))
    # The scan's fields before and after (null before an add / after a removal).
    previous: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    new: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reason: Mapped[str] = mapped_column(String(500))
    admin_id: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"))
    admin_name: Mapped[str] = mapped_column(String(120))  # kept even if the account is removed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
