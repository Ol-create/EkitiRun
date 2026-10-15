"""Kit collection endpoints. Owner: Lead (E15)."""

from fastapi import APIRouter

from app.core.schemas import error_responses
from app.modules.kit import service
from app.modules.kit.schemas import KitAssignIn, KitAssignOut, KitReturnIn, KitReturnOut

router = APIRouter(prefix="/kit", tags=["kit"])

# TODO(E15): require the PIN-unlocked volunteer device token on both endpoints.


@router.post("/assign", responses=error_responses(404, 409))
async def assign(body: KitAssignIn) -> KitAssignOut:
    return await service.assign(body)


@router.post("/return", responses=error_responses(404, 409))
async def return_tracker(body: KitReturnIn) -> KitReturnOut:
    return await service.return_tracker(body)
