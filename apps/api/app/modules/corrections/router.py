"""Race-office time correction endpoints. Owner: Lead (E17). Admin only."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.core.deps import CurrentAdmin, SessionDep
from app.core.redis import RedisDep
from app.core.schemas import error_responses
from app.modules.corrections import service
from app.modules.corrections.schemas import ChangeOut, RunnerTimesOut, SetTimeIn

router = APIRouter(prefix="/admin/runners/{bib_number}/scans", tags=["corrections"])


@router.get("", responses=error_responses(401, 404))
async def runner_times(bib_number: str, admin: CurrentAdmin, session: SessionDep) -> RunnerTimesOut:
    """A runner's time at every checkpoint on their course, and the correction history."""
    return await service.runner_times(session, bib_number)


@router.put("/{checkpoint_id}", responses=error_responses(401, 404, 409, 422))
async def set_time(
    bib_number: str,
    checkpoint_id: int,
    body: SetTimeIn,
    admin: CurrentAdmin,
    session: SessionDep,
    redis: RedisDep,
) -> ChangeOut:
    """Add or correct a runner's time at a checkpoint. It wins over phone scans."""
    return await service.set_time(
        session, redis, admin, bib_number, checkpoint_id, body.scanned_at, body.reason
    )


@router.delete("/{checkpoint_id}", responses=error_responses(401, 404, 409, 422))
async def remove_time(
    bib_number: str,
    checkpoint_id: int,
    reason: Annotated[str, Query(min_length=5, max_length=500)],
    admin: CurrentAdmin,
    session: SessionDep,
    redis: RedisDep,
) -> ChangeOut:
    """Remove a wrong scan (e.g. scanned at the wrong checkpoint). The original is kept
    in the history."""
    return await service.remove_time(session, redis, admin, bib_number, checkpoint_id, reason)
