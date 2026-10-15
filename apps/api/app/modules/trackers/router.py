"""Tracker inventory endpoints. Owner: Backend (B5)."""

from fastapi import APIRouter

from app.core.deps import AdminDep
from app.core.schemas import error_responses
from app.modules.trackers import service
from app.modules.trackers.schemas import TrackerIn, TrackerOut, TrackerPatch, TrackerStatus

router = APIRouter(
    prefix="/admin/trackers",
    tags=["trackers"],
    dependencies=[AdminDep],
    responses=error_responses(401),
)


@router.get("")
async def list_trackers(status: TrackerStatus | None = None) -> list[TrackerOut]:
    return await service.list_trackers(status)


@router.post("", status_code=201, responses=error_responses(409))
async def create_tracker(body: TrackerIn) -> TrackerOut:
    return await service.create_tracker(body)


@router.patch("/{tracker_id}", responses=error_responses(404))
async def update_tracker(tracker_id: int, body: TrackerPatch) -> TrackerOut:
    return await service.update_tracker(tracker_id, body)
