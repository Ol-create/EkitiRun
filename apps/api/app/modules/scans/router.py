"""scans endpoints. Owner: Lead (E8)."""

from fastapi import APIRouter

from app.core.deps import ScannerDep, SessionDep
from app.core.errors import AppError
from app.core.schemas import error_responses
from app.modules.scans import service
from app.modules.scans.schemas import ScanBatchIn, ScanBatchOut

router = APIRouter(prefix="/scans", tags=["scans"])


@router.post("/batch", responses=error_responses(401, 403))
async def ingest_batch(body: ScanBatchIn, device: ScannerDep, session: SessionDep) -> ScanBatchOut:
    """Scanner phones only (token from POST /scanner/login), for their own checkpoint."""
    if body.checkpoint_id != device.checkpoint_id:
        raise AppError(403, "WRONG_CHECKPOINT", "This phone is logged in to another checkpoint.")
    # The token's device id is the trusted one (the body's is informational).
    return await service.ingest_batch(session, device.device_id, body)
