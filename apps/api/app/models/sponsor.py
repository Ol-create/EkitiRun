"""Sponsor tier, sponsor and pledge models. Owner: Lead (E2).

Money is always stored in kobo (integer). Only the Paystack webhook (E5) may
set a pledge to `paid`.
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, UUIDPk

PLEDGE_STATUSES = ("pending", "paid", "failed")


class SponsorTier(Base):
    __tablename__ = "sponsor_tiers"
    __table_args__ = (CheckConstraint("amount_kobo > 0", name="amount_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60))
    amount_kobo: Mapped[int] = mapped_column(BigInteger)
    benefits: Mapped[list[str]] = mapped_column(ARRAY(String(200)), default=list)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Soft delete: old pledges still point to retired tiers (B1).
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Sponsor(UUIDPk, CreatedAt, Base):
    __tablename__ = "sponsors"

    company_name: Mapped[str] = mapped_column(String(120))
    contact_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254))
    phone: Mapped[str] = mapped_column(String(20))
    website: Mapped[str | None] = mapped_column(String(255))
    logo_url: Mapped[str | None] = mapped_column(String(500))


class Pledge(UUIDPk, CreatedAt, Base):
    __tablename__ = "pledges"
    __table_args__ = (
        CheckConstraint("amount_kobo > 0", name="amount_positive"),
        CheckConstraint(f"status IN {PLEDGE_STATUSES}", name="status_valid"),
    )

    sponsor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sponsors.id"), index=True)
    # Null for a custom amount.
    tier_id: Mapped[int | None] = mapped_column(ForeignKey("sponsor_tiers.id"))
    amount_kobo: Mapped[int] = mapped_column(BigInteger)
    reference: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    invoice_pdf_url: Mapped[str | None] = mapped_column(String(500))
    receipt_pdf_url: Mapped[str | None] = mapped_column(String(500))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
