"""Payment event model. Owner: Lead (E2, used by E5).

One row per verified provider event. The unique constraint makes webhook
handling idempotent: a replayed Paystack event can't be processed twice.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPk


class Payment(UUIDPk, Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_reference", "event", name="uq_payments_provider_event"
        ),
    )

    pledge_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pledges.id"), index=True)
    provider: Mapped[str] = mapped_column(String(20), default="paystack")
    provider_reference: Mapped[str] = mapped_column(String(64))
    event: Mapped[str] = mapped_column(String(40))  # e.g. charge.success
    amount_kobo: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(20))
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
