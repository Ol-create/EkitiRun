"""Stored file model. Owner: Lead (E6).

Generated documents (sponsor invoices and receipts) are kept in Postgres and
served by the API, so they need no extra storage service and survive redeploys.
The key contains a random token, so links can't be guessed.
"""

from sqlalchemy import Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, deferred, mapped_column

from app.models.base import Base, CreatedAt, UUIDPk


class StoredFile(UUIDPk, CreatedAt, Base):
    __tablename__ = "stored_files"

    # e.g. pledges/EKR-1A2B3C4D5E6F/invoice-<random token>.pdf
    key: Mapped[str] = mapped_column(String(255), unique=True)
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    # Deferred: listing files never loads their contents.
    data: Mapped[bytes] = deferred(mapped_column(LargeBinary))
