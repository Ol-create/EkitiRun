"""Passwords, OTPs, tokens, QR codes and device logins. Owner: Lead (E3, E4, E7, E15, E16)."""

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


# ---------------------------------------------------------------- checkpoint scanners (E7)

SCANNER_TOKEN_TTL = timedelta(hours=24)
_SCANNER_PURPOSE = "scanner"


def hash_pin(pin: str) -> str:
    """Keyed hash of a checkpoint PIN. Deterministic, so a PIN finds its checkpoint."""
    message = f"checkpoint-pin:{pin}".encode()
    return hmac.new(settings.jwt_secret.encode(), message, hashlib.sha256).hexdigest()


def create_scanner_token(device_id: str, checkpoint_id: int, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    claims = {
        "sub": device_id,
        "cp": checkpoint_id,
        "purpose": _SCANNER_PURPOSE,
        "iat": now,
        "exp": now + SCANNER_TOKEN_TTL,
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=_ALGORITHM)


# Kit-collection desks (E15) use the same kind of 24-hour device login.
_KIT_PURPOSE = "kit"


def kit_pin_matches(pin: str) -> bool:
    return hmac.compare_digest(pin.encode(), settings.kit_pin.encode())


def create_kit_token(device_id: str, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    claims = {"sub": device_id, "purpose": _KIT_PURPOSE, "iat": now, "exp": now + SCANNER_TOKEN_TTL}
    return jwt.encode(claims, settings.jwt_secret, algorithm=_ALGORITHM)


def parse_kit_token(token: str) -> str:
    """The kit desk's device id, or 401 KIT_AUTH_REQUIRED."""
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[_ALGORITHM],
            options={"require": ["sub", "exp", "purpose"]},
        )
    except jwt.InvalidTokenError:
        raise AppError(
            401, "KIT_AUTH_REQUIRED", "Kit desk login expired. Enter the PIN again."
        ) from None
    if claims.get("purpose") != _KIT_PURPOSE:
        raise AppError(401, "KIT_AUTH_REQUIRED", "Not a kit desk login.")
    return str(claims["sub"])


def parse_scanner_token(token: str) -> tuple[str, int]:
    """(device_id, checkpoint_id), or 401 SCANNER_AUTH_REQUIRED."""
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[_ALGORITHM],
            options={"require": ["sub", "exp", "purpose", "cp"]},
        )
    except jwt.InvalidTokenError:
        raise AppError(
            401, "SCANNER_AUTH_REQUIRED", "Scanner login expired. Enter the checkpoint PIN again."
        ) from None
    if claims.get("purpose") != _SCANNER_PURPOSE:
        raise AppError(401, "SCANNER_AUTH_REQUIRED", "Not a scanner login.")
    return str(claims["sub"]), int(claims["cp"])


# ---------------------------------------------------------------- admin accounts (E16)

ADMIN_TOKEN_TTL = timedelta(hours=12)  # one race day
_ADMIN_PURPOSE = "admin"
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1  # ~16 MB and ~50 ms per check
MIN_PASSWORD_LENGTH = 12


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=32)


def hash_password(password: str) -> str:
    """`scrypt$N$r$p$salt$hash` (base64). Slow on purpose, so stolen hashes resist guessing."""
    salt = secrets.token_bytes(16)
    digest = _scrypt(password, salt, _SCRYPT_N, _SCRYPT_R, _SCRYPT_P)
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${b64(salt)}${b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        actual = _scrypt(password, base64.b64decode(salt), int(n), int(r), int(p))
        return hmac.compare_digest(actual, base64.b64decode(digest))
    except (ValueError, TypeError):
        return False


# Checked against when the email is unknown, so a wrong email takes as long as a
# wrong password and response times don't reveal which admin emails exist.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def burn_password_check(password: str) -> None:
    verify_password(password, _DUMMY_HASH)


def create_admin_token(admin_id: int, session_version: int, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    claims = {
        "sub": str(admin_id),
        "sv": session_version,
        "purpose": _ADMIN_PURPOSE,
        "iat": now,
        "exp": now + ADMIN_TOKEN_TTL,
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=_ALGORITHM)


def parse_admin_token(token: str) -> tuple[int, int] | None:
    """(admin id, session version), or None if this isn't a valid admin token."""
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[_ALGORITHM],
            options={"require": ["sub", "exp", "purpose", "sv"]},
        )
    except jwt.InvalidTokenError:
        return None
    if claims.get("purpose") != _ADMIN_PURPOSE:
        return None
    try:
        return int(claims["sub"]), int(claims["sv"])
    except (TypeError, ValueError):
        return None
