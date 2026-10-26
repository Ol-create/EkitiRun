"""Admin account model. Owner: Lead (E16).

There is no sign-up: admins are created with `python -m scripts.create_admin`.
Only a scrypt hash of the password is stored. Bumping `session_version` signs the
admin out everywhere (every token carries the version it was issued with).
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt


class AdminUser(CreatedAt, Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)  # stored lower-case
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    session_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
