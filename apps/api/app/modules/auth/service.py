"""Database and business logic for auth. Routers call this; it never imports FastAPI.

STUB(E3): fake OTP flow, so the frontend can build its screens. Stub rules:
- Phone ending in 1111: request is rate limited (429 OTP_RATE_LIMITED).
- Code 123456 is valid; 000000 is expired; anything else is invalid.
"""

from app.core.errors import AppError

STUB_TOKEN_PREFIX = "stub."


async def request_otp(phone: str) -> None:
    if phone.endswith("1111"):
        raise AppError(429, "OTP_RATE_LIMITED", "Too many codes requested. Try again in a minute.")


async def verify_otp(phone: str, code: str) -> str:
    if code == "000000":
        raise AppError(400, "OTP_EXPIRED", "This code has expired. Request a new one.")
    if code != "123456":
        raise AppError(400, "OTP_INVALID", "That code is not correct.")
    return f"{STUB_TOKEN_PREFIX}{phone}"


def phone_from_verification_token(token: str) -> str:
    if not token.startswith(STUB_TOKEN_PREFIX):
        raise AppError(401, "VERIFICATION_INVALID", "Phone verification expired. Verify again.")
    return token.removeprefix(STUB_TOKEN_PREFIX)
