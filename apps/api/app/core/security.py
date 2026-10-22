"""OTP hashing, phone-verification tokens and signed QR tokens. Owner: Lead (E3, E4)."""

import base64
import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import settings
from app.core.errors import AppError

VERIFICATION_TOKEN_TTL = timedelta(minutes=30)
_VERIFICATION_PURPOSE = "phone_verification"
_ALGORITHM = "HS256"


def generate_otp() -> str:
    if settings.environment != "production" and settings.otp_dev_code:
        return settings.otp_dev_code
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(phone: str, code: str) -> str:
    """Keyed hash: a leaked table can't be brute-forced without the server secret."""
    message = f"otp:{phone}:{code}".encode()
    return hmac.new(settings.jwt_secret.encode(), message, hashlib.sha256).hexdigest()


def otp_matches(phone: str, code: str, code_hash: str) -> bool:
    return hmac.compare_digest(hash_otp(phone, code), code_hash)


def create_verification_token(phone: str, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    claims = {
        "sub": phone,
        "purpose": _VERIFICATION_PURPOSE,
        "iat": now,
        "exp": now + VERIFICATION_TOKEN_TTL,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=_ALGORITHM)


def phone_from_verification_token(token: str) -> str:
    """The verified phone number, or 401 VERIFICATION_INVALID."""
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[_ALGORITHM],
            options={"require": ["sub", "exp", "purpose"]},
        )
    except jwt.ExpiredSignatureError:
        raise AppError(
            401, "VERIFICATION_INVALID", "Phone verification expired. Verify again."
        ) from None
    except jwt.InvalidTokenError:
        raise AppError(401, "VERIFICATION_INVALID", "Phone verification is not valid.") from None
    if claims.get("purpose") != _VERIFICATION_PURPOSE:
        raise AppError(401, "VERIFICATION_INVALID", "Phone verification is not valid.")
    return str(claims["sub"])


# ---------------------------------------------------------------- runner QR codes (E4)

_QR_VERSION = "R1"
_QR_SIG_BYTES = 16  # 128-bit signature: short enough for a small, fast-scanning QR


def _qr_signature(bib_number: str, runner_id: uuid.UUID) -> str:
    message = f"{_QR_VERSION}.{bib_number}.{runner_id.hex}".encode()
    digest = hmac.new(settings.qr_signing_secret.encode(), message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest[:_QR_SIG_BYTES]).decode().rstrip("=")


def create_qr_token(bib_number: str, runner_id: uuid.UUID) -> str:
    """What the runner's QR code contains, e.g. `R1.H0042.<runner id>.<signature>`.

    Changing the bib or runner id breaks the signature, so a printed code can't
    be edited into someone else's.
    """
    return f"{_QR_VERSION}.{bib_number}.{runner_id.hex}.{_qr_signature(bib_number, runner_id)}"


def parse_qr_token(token: str) -> tuple[uuid.UUID, str]:
    """(runner_id, bib_number) from a scanned QR token, or 400 QR_INVALID."""
    parts = token.strip().split(".")
    if len(parts) == 4 and parts[0] == _QR_VERSION:
        _, bib_number, runner_hex, signature = parts
        try:
            runner_id = uuid.UUID(hex=runner_hex)
        except ValueError:
            pass
        else:
            if hmac.compare_digest(signature, _qr_signature(bib_number, runner_id)):
                return runner_id, bib_number
    raise AppError(400, "QR_INVALID", "This QR code is not a valid EkitiRun bib.")
