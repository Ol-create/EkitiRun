"""Runner model. Owner: Lead (E2).

Phone, email, date of birth and emergency contact are private: never return
them from public endpoints.
"""

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, UUIDPk

RUNNER_STATUSES = ("registered", "started", "finished", "dnf")


class Runner(UUIDPk, CreatedAt, Base):
    __tablename__ = "runners"
    __table_args__ = (
        CheckConstraint("gender IN ('M', 'F')", name="gender_valid"),
        CheckConstraint(f"status IN {RUNNER_STATUSES}", name="status_valid"),
    )

    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)
    bib_number: Mapped[str] = mapped_column(String(8), unique=True)
    first_name: Mapped[str] = mapped_column(String(60))
    last_name: Mapped[str] = mapped_column(String(60))
    gender: Mapped[str] = mapped_column(String(1))
    date_of_birth: Mapped[date] = mapped_column(Date)
    phone: Mapped[str] = mapped_column(String(20), unique=True)  # +234...
    email: Mapped[str | None] = mapped_column(String(254))
    emergency_contact_name: Mapped[str] = mapped_column(String(120))
    emergency_contact_phone: Mapped[str] = mapped_column(String(20))
    # When the runner agreed to wear a GPS tracker. Registration requires it.
    tracking_consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(16), default="registered", server_default="registered"
    )
    kit_collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
