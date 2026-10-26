"""Admin login. Owner: Lead (E16).

- Accounts come from `python -m scripts.create_admin` (no sign-up endpoint).
- A login returns a 12-hour token; every admin request re-checks the account.
- Wrong passwords are limited to 5 per email and 10 per IP address per 15 minutes,
  and an unknown email takes as long to reject as a wrong password.
"""

from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.errors import AppError
from app.models import AdminUser
from app.modules.admin_auth.schemas import AdminLoginOut, AdminOut

WINDOW_S = 15 * 60
MAX_FAILURES_PER_EMAIL = 5
MAX_FAILURES_PER_IP = 10


def _keys(email: str, client_ip: str) -> tuple[str, str]:
    return f"admin-login:email:{email}", f"admin-login:ip:{client_ip}"


async def _too_many(redis: Redis, email_key: str, ip_key: str) -> bool:
    by_email, by_ip = await redis.mget(email_key, ip_key)
    return int(by_email or 0) >= MAX_FAILURES_PER_EMAIL or int(by_ip or 0) >= MAX_FAILURES_PER_IP


async def _record_failure(redis: Redis, email_key: str, ip_key: str) -> None:
    async with redis.pipeline(transaction=True) as pipe:
        for key in (email_key, ip_key):
            pipe.incr(key)
            pipe.expire(key, WINDOW_S, nx=True)
        await pipe.execute()


async def login(
    session: AsyncSession, redis: Redis, email: str, password: str, client_ip: str
) -> AdminLoginOut:
    email = email.strip().lower()
    email_key, ip_key = _keys(email, client_ip)
    if await _too_many(redis, email_key, ip_key):
        raise AppError(429, "LOGIN_RATE_LIMITED", "Too many failed sign-ins. Wait 15 minutes.")

    admin = await session.scalar(select(AdminUser).where(AdminUser.email == email))
    if admin is None:
        security.burn_password_check(password)
        ok = False
    else:
        ok = security.verify_password(password, admin.password_hash) and admin.is_active
    if not ok or admin is None:
        await _record_failure(redis, email_key, ip_key)
        raise AppError(401, "LOGIN_INVALID", "Email or password is not correct.")

    now = datetime.now(UTC)
    admin.last_login_at = now
    await session.commit()
    await redis.delete(email_key)  # a successful sign-in clears this email's failures
    return AdminLoginOut(
        token=security.create_admin_token(admin.id, admin.session_version, now),
        expires_at=now + security.ADMIN_TOKEN_TTL,
        admin=AdminOut.model_validate(admin),
    )
