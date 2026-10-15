"""Phone verification by SMS code (OTP). Owner: Lead (E3).

Flow: request_otp() texts a 6-digit code; verify_otp() checks it and returns a
signed verification token that POST /registrations requires.

Rules:
- A code is valid for 10 minutes and can be guessed at most 5 times.
- Requesting a new code cancels the previous one.
- 1 request per phone per 60 s, and 10 per IP address per hour (Redis).
- Only a keyed hash of the code is stored.
"""

from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.errors import AppError
from app.core.redis import claim_cooldown, cooldown_left_s, hit_fixed_window
from app.core.sms import SmsSender, SmsSendError
from app.models import OtpCode

CODE_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 5
PHONE_COOLDOWN_S = 60
IP_LIMIT_PER_HOUR = 10


def _sms_text(code: str) -> str:
    return f"Your EkitiRun verification code is {code}. It expires in 10 minutes."


async def request_otp(
    session: AsyncSession, redis: Redis, sms: SmsSender, phone: str, client_ip: str
) -> None:
    phone_key = f"otp:cooldown:{phone}"
    if not await claim_cooldown(redis, phone_key, PHONE_COOLDOWN_S):
        wait = await cooldown_left_s(redis, phone_key)
        raise AppError(
            429, "OTP_RATE_LIMITED", f"Please wait {wait} seconds before requesting a new code."
        )
    if not await hit_fixed_window(redis, f"otp:ip:{client_ip}", IP_LIMIT_PER_HOUR, 3600):
        raise AppError(429, "OTP_RATE_LIMITED", "Too many codes requested. Try again later.")

    code = security.generate_otp()
    await session.execute(
        delete(OtpCode).where(OtpCode.phone == phone, OtpCode.consumed_at.is_(None))
    )
    session.add(
        OtpCode(
            phone=phone,
            code_hash=security.hash_otp(phone, code),
            expires_at=datetime.now(UTC) + CODE_TTL,
        )
    )
    try:
        await sms.send(phone, _sms_text(code))
    except SmsSendError:
        await session.rollback()
        await redis.delete(phone_key)  # let them retry straight away
        raise AppError(
            502, "SMS_SEND_FAILED", "We couldn't send the SMS. Please try again."
        ) from None
    await session.commit()


async def verify_otp(session: AsyncSession, phone: str, code: str) -> str:
    otp = await session.scalar(
        select(OtpCode)
        .where(OtpCode.phone == phone, OtpCode.consumed_at.is_(None))
        .order_by(OtpCode.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    if otp is None:
        raise AppError(400, "OTP_INVALID", "That code is not correct. Request a new one.")
    if otp.expires_at <= datetime.now(UTC):
        raise AppError(400, "OTP_EXPIRED", "This code has expired. Request a new one.")
    if otp.attempts >= MAX_ATTEMPTS:
        raise AppError(429, "OTP_TOO_MANY_ATTEMPTS", "Too many wrong codes. Request a new one.")

    if not security.otp_matches(phone, code, otp.code_hash):
        otp.attempts += 1
        await session.commit()
        left = MAX_ATTEMPTS - otp.attempts
        raise AppError(
            400,
            "OTP_INVALID",
            f"That code is not correct. {left} attempt{'s' if left != 1 else ''} left."
            if left
            else "That code is not correct. Request a new one.",
        )

    otp.consumed_at = datetime.now(UTC)
    await session.commit()
    return security.create_verification_token(phone)
