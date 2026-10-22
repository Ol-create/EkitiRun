"""Runner registration, bib numbers and QR codes. Owner: Lead (E4).

Registration is free. The order of checks matters:
1. Tracking consent and the verified phone (from the OTP token).
2. The category row is locked (`SELECT ... FOR UPDATE`), so only one
   registration at a time can take a place in it: caps can't be exceeded and
   two runners can never get the same bib.
3. Cap, age on race day and duplicate phone are checked under the lock.
4. The runner gets the category's next bib (F0001, H0001, ...).
"""

import io
import uuid
from datetime import UTC, date, datetime, timedelta, timezone

import segno
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.core.schemas import CategorySummary
from app.core.security import create_qr_token, phone_from_verification_token
from app.models import Category, Runner
from app.modules.registrations.schemas import RegistrationIn, RegistrationOut

LAGOS = timezone(timedelta(hours=1))  # WAT, no daylight saving


def bib_for(category: Category, number: int) -> str:
    return f"{category.bib_prefix}{number:04d}"


def age_on(birth: date, day: date) -> int:
    return day.year - birth.year - ((day.month, day.day) < (birth.month, birth.day))


def race_day(category: Category) -> date:
    if category.gun_start_at is not None:
        return category.gun_start_at.astimezone(LAGOS).date()
    return settings.race_date or datetime.now(LAGOS).date()


def qr_png_url(runner_id: uuid.UUID) -> str:
    return f"{settings.public_api_url}/api/v1/registrations/{runner_id}/qr.png"


async def register(session: AsyncSession, body: RegistrationIn) -> RegistrationOut:
    if not body.tracking_consent:
        raise AppError(
            422,
            "TRACKING_CONSENT_REQUIRED",
            "Every runner wears a GPS tracker. Please agree to live tracking to register.",
        )
    phone = phone_from_verification_token(body.verification_token)

    category = await session.scalar(
        select(Category).where(Category.id == body.category_id).with_for_update()
    )
    if category is None:
        raise AppError(404, "CATEGORY_NOT_FOUND", "That category does not exist.")

    if await session.scalar(select(Runner.id).where(Runner.phone == phone)):
        raise AppError(409, "PHONE_ALREADY_REGISTERED", "This phone number is already registered.")

    registered = await session.scalar(
        select(func.count()).select_from(Runner).where(Runner.category_id == category.id)
    )
    if (registered or 0) >= category.cap:
        raise AppError(409, "CATEGORY_FULL", f"Sorry, the {category.name} is full.")

    if age_on(body.date_of_birth, race_day(category)) < category.min_age:
        raise AppError(
            422,
            "AGE_REQUIREMENT_NOT_MET",
            f"You must be at least {category.min_age} on race day for the {category.name}.",
        )

    runner = Runner(
        id=uuid.uuid4(),
        category_id=category.id,
        bib_number=bib_for(category, category.next_bib),
        first_name=body.first_name,
        last_name=body.last_name,
        gender=body.gender,
        date_of_birth=body.date_of_birth,
        phone=phone,
        email=body.email.lower() if body.email else None,
        emergency_contact_name=body.emergency_contact_name,
        emergency_contact_phone=body.emergency_contact_phone,
        tracking_consent_at=datetime.now(UTC),
    )
    category.next_bib += 1
    session.add(runner)
    try:
        await session.commit()
    except IntegrityError as exc:
        # Two sign-ups with the same phone in different categories at the same moment.
        await session.rollback()
        if "uq_runners_phone" in str(exc.orig):
            raise AppError(
                409, "PHONE_ALREADY_REGISTERED", "This phone number is already registered."
            ) from None
        raise

    return RegistrationOut(
        runner_id=runner.id,
        bib_number=runner.bib_number,
        category=CategorySummary(id=category.id, code=category.code, name=category.name),
        qr_png_url=qr_png_url(runner.id),
    )


async def qr_png(session: AsyncSession, runner_id: uuid.UUID) -> bytes:
    runner = await session.get(Runner, runner_id)
    if runner is None:
        raise AppError(404, "RUNNER_NOT_FOUND", "No runner with that id.")
    buf = io.BytesIO()
    qr = segno.make(create_qr_token(runner.bib_number, runner.id), error="m")
    qr.save(buf, kind="png", scale=8, border=2)
    return buf.getvalue()
