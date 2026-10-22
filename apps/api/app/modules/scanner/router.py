"""Checkpoint scanner endpoints. Owner: Lead (E7, E8)."""

from fastapi import APIRouter, Request

from app.core.deps import AdminDep, ScannerDep, SessionDep
from app.core.redis import RedisDep
from app.core.schemas import error_responses
from app.modules.scanner import service
from app.modules.scanner.schemas import RosterOut, ScannerDeviceOut, ScannerLoginIn, ScannerLoginOut

router = APIRouter(prefix="/scanner", tags=["scanner"])


@router.post("/login", responses=error_responses(401, 429))
async def login(
    body: ScannerLoginIn, request: Request, session: SessionDep, redis: RedisDep
) -> ScannerLoginOut:
    client_ip = request.client.host if request.client else "unknown"
    return await service.login(session, redis, body.pin, body.device_id, client_ip)


@router.get("/roster", responses=error_responses(401))
async def roster(device: ScannerDep, session: SessionDep) -> RosterOut:
    """Runners on this checkpoint's course, for showing names while offline."""
    return await service.roster(session, device.checkpoint_id)


@router.get(
    "/devices",
    dependencies=[AdminDep],
    responses=error_responses(401),
)
async def list_devices(session: SessionDep) -> list[ScannerDeviceOut]:
    """Admin: scanner phones, with their last upload and whether their clock is off."""
    return await service.list_devices(session)
