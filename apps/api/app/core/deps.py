"""Shared FastAPI dependencies. Owner: Lead.

Newbies import from here (e.g. `require_admin`, `SessionDep`) but don't change it.
"""

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_session
from app.core.errors import AppError

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


async def require_gateway(x_gateway_secret: Annotated[str | None, Header()] = None) -> None:
    """GPS gateway (Traccar) only, authenticated with the `X-Gateway-Secret` header."""
    if x_gateway_secret != settings.gateway_secret:
        raise AppError(401, "GATEWAY_AUTH_REQUIRED", "Gateway secret missing or invalid")


AdminDep = Depends(require_admin)
GatewayDep = Depends(require_gateway)
