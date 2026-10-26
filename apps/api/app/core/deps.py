"""Shared FastAPI dependencies. Owner: Lead.

Newbies import from here (e.g. `require_admin`, `SessionDep`) but don't change it.
"""

import hmac
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_session
from app.core.errors import AppError
from app.core.security import parse_admin_token, parse_kit_token, parse_scanner_token
from app.models import AdminUser

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def require_admin(
    session: SessionDep, authorization: Annotated[str | None, Header()] = None
) -> AdminUser | None:
    """Admin-only endpoints: `Authorization: Bearer <token from POST /admin/auth/login>`.

    The account is re-checked on every request, so deactivating an admin or signing
    them out everywhere (scripts/create_admin.py) takes effect at once.
    In development only, `Bearer <ADMIN_DEV_TOKEN>` (default `dev-admin`) also works,
    returning None instead of an admin.
    """
    token = (authorization or "").removeprefix("Bearer ").strip()
    if settings.environment != "production" and token and token == settings.admin_dev_token:
        return None
    parsed = parse_admin_token(token) if token else None
    if parsed is not None:
        admin = await session.get(AdminUser, parsed[0])
        if admin is not None and admin.is_active and admin.session_version == parsed[1]:
            return admin
    raise AppError(401, "ADMIN_AUTH_REQUIRED", "Admin login required. Sign in again.")


CurrentAdmin = Annotated[AdminUser | None, Depends(require_admin)]


async def require_gateway(
    x_gateway_secret: Annotated[str | None, Header()] = None,
    secret: Annotated[str | None, Query(include_in_schema=False)] = None,
) -> None:
    """GPS gateway (Traccar) only: the `X-Gateway-Secret` header, or `?secret=` for
    gateways that can't add headers."""
    given = x_gateway_secret or secret or ""
    if not hmac.compare_digest(given.encode(), settings.gateway_secret.encode()):
        raise AppError(401, "GATEWAY_AUTH_REQUIRED", "Gateway secret missing or invalid")


AdminDep = Depends(require_admin)
GatewayDep = Depends(require_gateway)


@dataclass(frozen=True)
class ScannerDevice:
    device_id: str
    checkpoint_id: int


async def require_scanner(authorization: Annotated[str | None, Header()] = None) -> ScannerDevice:
    """Checkpoint scanner phones: `Authorization: Bearer <token from POST /scanner/login>`."""
    if not authorization or not authorization.startswith("Bearer "):
        raise AppError(
            401, "SCANNER_AUTH_REQUIRED", "Scanner login expired. Enter the checkpoint PIN again."
        )
    device_id, checkpoint_id = parse_scanner_token(authorization.removeprefix("Bearer "))
    return ScannerDevice(device_id, checkpoint_id)


ScannerDep = Annotated[ScannerDevice, Depends(require_scanner)]


async def require_kit_desk(authorization: Annotated[str | None, Header()] = None) -> str:
    """Kit-collection and return desks: `Authorization: Bearer <token from POST /kit/login>`."""
    if not authorization or not authorization.startswith("Bearer "):
        raise AppError(401, "KIT_AUTH_REQUIRED", "Kit desk login expired. Enter the PIN again.")
    return parse_kit_token(authorization.removeprefix("Bearer "))


KitDeskDep = Annotated[str, Depends(require_kit_desk)]
