"""Race-office timing controls. Owner: Lead (E9). Admin only."""

from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import select

from app.core.bibs import normalize_bib
from app.core.deps import AdminDep, SessionDep
from app.core.errors import AppError
from app.core.redis import RedisDep
from app.core.schemas import error_responses
from app.models import Category, Runner
from app.modules.timing import service
from app.modules.timing.schemas import GunStartIn, GunStartOut, RunnerStatusOut

router = APIRouter(prefix="/admin", tags=["timing"], dependencies=[AdminDep])


@router.post("/categories/{category_id}/gun-start", responses=error_responses(401, 404))
async def gun_start(
    category_id: int, body: GunStartIn, session: SessionDep, redis: RedisDep
) -> GunStartOut:
    """Record the category's start time. All elapsed times are measured from it."""
    category = await session.get(Category, category_id)
    if category is None:
        raise AppError(404, "CATEGORY_NOT_FOUND", "That category does not exist.")
    category.gun_start_at = body.at or datetime.now(UTC)
    await session.commit()
    await service.mark_changed(redis, {category.id})
    return GunStartOut(
        category_id=category.id, category_code=category.code, gun_start_at=category.gun_start_at
    )


async def _set_status(session, redis, bib_number: str, status: str) -> RunnerStatusOut:
    bib = normalize_bib(bib_number)
    runner = await session.scalar(select(Runner).where(Runner.bib_number == bib))
    if runner is None:
        raise AppError(404, "RUNNER_NOT_FOUND", f"No runner with bib {bib}.")
    runner.status = status
    await session.commit()
    await service.mark_changed(redis, {runner.category_id})
    return RunnerStatusOut(bib_number=runner.bib_number, status=status)


@router.post("/runners/{bib_number}/dnf", responses=error_responses(401, 404))
async def mark_dnf(bib_number: str, session: SessionDep, redis: RedisDep) -> RunnerStatusOut:
    """Mark a runner as did-not-finish (dropped out, picked up by the sweeper bus)."""
    return await _set_status(session, redis, bib_number, "dnf")


@router.delete("/runners/{bib_number}/dnf", responses=error_responses(401, 404))
async def undo_dnf(bib_number: str, session: SessionDep, redis: RedisDep) -> RunnerStatusOut:
    """Undo a DNF marked by mistake. Status then comes from the runner's scans again."""
    return await _set_status(session, redis, bib_number, "registered")
