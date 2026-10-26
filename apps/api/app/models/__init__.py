"""SQLAlchemy models. Owner: Lead (E2). Ask Lead before changing anything here.

Every model must be imported here so Alembic can see it.
"""

from app.models.admin import AdminUser
from app.models.base import Base
from app.models.category import Category
from app.models.checkpoint import Checkpoint
from app.models.otp import OtpCode
from app.models.payment import Payment
from app.models.route import Route
from app.models.runner import Runner
from app.models.scan import Scan
from app.models.scanner_device import ScannerDevice
from app.models.sponsor import Pledge, Sponsor, SponsorTier
from app.models.stored_file import StoredFile
from app.models.tracker import GpsPosition, Tracker

__all__ = [
    "AdminUser",
    "Base",
    "Category",
    "Checkpoint",
    "GpsPosition",
    "OtpCode",
    "Payment",
    "Pledge",
    "Route",
    "Runner",
    "Scan",
    "ScannerDevice",
    "Sponsor",
    "SponsorTier",
    "StoredFile",
    "Tracker",
]
