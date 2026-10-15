"""Category model. Owner: Lead (E2)."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint("cap > 0", name="cap_positive"),
        CheckConstraint("next_bib > 0", name="next_bib_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(8), unique=True)  # FULL, HALF, 10K, FUN
    name: Mapped[str] = mapped_column(String(60))
    distance_km: Mapped[Decimal] = mapped_column(Numeric(7, 4))
    cap: Mapped[int] = mapped_column(Integer)
    # Bib numbers are prefix + zero-padded counter, e.g. F0001 (E4).
    bib_prefix: Mapped[str] = mapped_column(String(1), unique=True)
    next_bib: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    min_age: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id"))
    gun_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
