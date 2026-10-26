"""Admin login endpoints. Owner: Lead (E16)."""

from fastapi import APIRouter, Request

from app.core.deps import CurrentAdmin, SessionDep
from app.core.errors import AppError
from app.core.redis import RedisDep
from app.core.schemas import error_responses
from app.modules.admin_auth import service
from app.modules.admin_auth.schemas import AdminLoginIn, AdminLoginOut, AdminOut

router = APIRouter(prefix="/admin/auth", tags=["admin"])


@router.post("/login", responses=error_responses(401, 429))
async def login(
    body: AdminLoginIn, request: Request, session: SessionDep, redis: RedisDep
) -> AdminLoginOut:
    """Sign in an organiser. The token lasts 12 hours."""
    client_ip = request.client.host if request.client else "unknown"
    return await service.login(session, redis, body.email, body.password, client_ip)


@router.get("/me", responses=error_responses(401))
async def me(admin: CurrentAdmin) -> AdminOut:
    """Who this token belongs to (to check a stored token is still valid)."""
    if admin is None:  # the development token has no account behind it
        raise AppError(404, "DEV_TOKEN", "Signed in with the development token, not an account.")
    return AdminOut.model_validate(admin)
