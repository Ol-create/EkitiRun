"""scans endpoints. Owner: Lead (E8)."""

from fastapi import APIRouter

from app.modules.scans import service
from app.modules.scans.schemas import ScanBatchIn, ScanBatchOut

router = APIRouter(prefix="/scans", tags=["scans"])


@router.post("/batch")
async def ingest_batch(body: ScanBatchIn) -> ScanBatchOut:
    # TODO(E7/E8): require the scanner device token bound to this checkpoint.
    return await service.ingest_batch(body)
