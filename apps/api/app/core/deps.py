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
from app.core.security import parse_scanner_token

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def require_admin(authorization: Annotated[str | None, Header()] = None) -> None:
    """Admin-only endpoints.

    Until real admin login is built, development accepts
    `Authorization: Bearer <ADMIN_DEV_TOKEN>` (default `dev-admin`).
    """
    # TODO(Lead): verify a real admin login here (not yet scheduled in a ticket).
    if settings.environment == "production":
        raise AppError(401, "ADMIN_AUTH_REQUIRED", "Admin login is not available yet")
    if authorization != f"Bearer {settings.admin_dev_token}":
        raise AppError(401, "ADMIN_AUTH_REQUIRED", "Admin token missing or invalid")


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
