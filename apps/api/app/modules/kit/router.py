"""Kit collection and tracker return endpoints. Owner: Lead (E15)."""

from fastapi import APIRouter, Request

from app.core.deps import KitDeskDep, SessionDep
from app.core.redis import RedisDep
from app.core.schemas import error_responses
from app.modules.kit import service
from app.modules.kit.schemas import (
    KitAssignIn,
    KitAssignOut,
    KitLoginIn,
    KitLoginOut,
    KitReturnIn,
    KitReturnOut,
    OutstandingOut,
)

router = APIRouter(prefix="/kit", tags=["kit"])


@router.post("/login", responses=error_responses(401, 429))
async def login(body: KitLoginIn, request: Request, redis: RedisDep) -> KitLoginOut:
    """Unlock a kit-collection or return desk with the kit PIN (KIT_PIN). Lasts 24 h."""
    client_ip = request.client.host if request.client else "unknown"
    return await service.login(redis, body.pin, body.device_id, client_ip)


@router.post("/assign", responses=error_responses(400, 401, 404, 409))
async def assign(body: KitAssignIn, desk: KitDeskDep, session: SessionDep) -> KitAssignOut:
    """Hand a tracker to a runner. Scanning the same pair again is harmless."""
    return await service.assign(session, body)


@router.post("/return", responses=error_responses(401, 404, 409))
async def return_tracker(
    body: KitReturnIn, desk: KitDeskDep, session: SessionDep, redis: RedisDep
) -> KitReturnOut:
    """Take a tracker back (finish area or kit desk)."""
    return await service.return_tracker(session, redis, body.tracker_label)


@router.get("/outstanding", responses=error_responses(401))
async def outstanding(desk: KitDeskDep, session: SessionDep, redis: RedisDep) -> OutstandingOut:
    """Trackers still out and who has them."""
    return await service.outstanding(session, redis)
