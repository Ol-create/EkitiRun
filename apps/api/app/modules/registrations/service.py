"""Database and business logic for registrations. Routers call this; it never imports FastAPI.

STUB(E4): nothing is saved. Stub rules (by the verified phone number):
- Phone ending in 0000: 409 PHONE_ALREADY_REGISTERED.
- Phone ending in 9999: 409 CATEGORY_FULL.
"""

import io
import itertools
import uuid

import segno

from app.core.config import settings
from app.core.errors import AppError
from app.core.schemas import CategorySummary
from app.modules.auth.service import phone_from_verification_token
from app.modules.registrations.schemas import RegistrationIn, RegistrationOut
from app.stubs import race

# Stub bibs start at 1001 so they never clash with the fake runners (0001-0070).
_bib_counter = itertools.count(1001)


async def register(body: RegistrationIn) -> RegistrationOut:
    if not body.tracking_consent:
        raise AppError(
            422,
            "TRACKING_CONSENT_REQUIRED",
            "Every runner wears a GPS tracker. Please agree to live tracking to register.",
        )
    phone = phone_from_verification_token(body.verification_token)
    category = next((c for c in race.categories() if c["id"] == body.category_id), None)
    if category is None:
        raise AppError(404, "CATEGORY_NOT_FOUND", "That category does not exist.")
    if phone.endswith("0000"):
        raise AppError(409, "PHONE_ALREADY_REGISTERED", "This phone number is already registered.")
    if phone.endswith("9999"):
        raise AppError(409, "CATEGORY_FULL", f"{category['name']} is full.")

    runner_id = uuid.uuid4()
    return RegistrationOut(
        runner_id=runner_id,
        bib_number=f"{category['bib_prefix']}{next(_bib_counter):04d}",
        category=CategorySummary(id=category["id"], code=category["code"], name=category["name"]),
        qr_png_url=f"{settings.public_api_url}/api/v1/registrations/{runner_id}/qr.png",
    )


def qr_png(runner_id: uuid.UUID) -> bytes:
    # TODO(E4): encode the HMAC-signed QR token instead of this placeholder.
    buf = io.BytesIO()
    segno.make(f"STUB:{runner_id}", error="m").save(buf, kind="png", scale=8, border=2)
    return buf.getvalue()
