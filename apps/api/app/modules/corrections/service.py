"""Race-office time corrections. Owner: Lead (E17).

For paper backup sheets, a scanner phone that died, or a wrong time:
- set (add or correct) a runner's time at a checkpoint, or remove a wrong scan;
- a reason is required, and every change is written to `scan_corrections` with the
  values before and after and who made it, so the original is never lost;
- the time the office enters wins outright (phone uploads never overwrite it);
- the leaderboard refreshes and the change goes out on the live stream, like a scan.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.bibs import normalize_bib
from app.core.broadcast import publish
from app.core.errors import AppError
from app.models import AdminUser, Category, Checkpoint, Runner, Scan, ScanCorrection
from app.modules.corrections.schemas import (
    ChangeOut,
    CheckpointTime,
    Correction,
    RunnerTimesOut,
)
from app.modules.results.schemas import SCANS_CHANNEL, ScanEvent
from app.modules.timing import service as timing

log = logging.getLogger("ekitirun.corrections")
MAX_FUTURE = timedelta(minutes=10)


def _snapshot(scan: Scan) -> dict[str, Any]:
    return {
        "scanned_at": scan.scanned_at.isoformat(),
        "clock_offset_ms": scan.clock_offset_ms,
        "corrected_at": timing.corrected_time(scan).isoformat(),
        "device_id": scan.device_id,
        "entry": scan.entry,
        "client_id": str(scan.client_id),
    }


async def _runner(session: AsyncSession, bib: str) -> tuple[Runner, Category]:
    bib = normalize_bib(bib)
    runner = await session.scalar(select(Runner).where(Runner.bib_number == bib).with_for_update())
    if runner is None:
        raise AppError(404, "RUNNER_NOT_FOUND", f"No runner with bib {bib}.")
    category = await session.get(Category, runner.category_id)
    assert category is not None
    return runner, category


async def _checkpoint(session: AsyncSession, category: Category, checkpoint_id: int) -> Checkpoint:
    checkpoint = await session.get(Checkpoint, checkpoint_id)
    if checkpoint is None:
        raise AppError(404, "CHECKPOINT_NOT_FOUND", "That checkpoint does not exist.")
    if checkpoint.route_id != category.route_id:
        raise AppError(
            409, "WRONG_COURSE", f"{checkpoint.name} isn't on the {category.name} course."
        )
    return checkpoint


def _time(checkpoint: Checkpoint, scan: Scan | None, gun: datetime | None) -> CheckpointTime:
    at = timing.corrected_time(scan) if scan else None
    return CheckpointTime(
        checkpoint_id=checkpoint.id,
        checkpoint_code=checkpoint.code,
        checkpoint_name=checkpoint.name,
        distance_km=float(checkpoint.distance_km),
        scanned_at=at,
        elapsed_seconds=timing.elapsed(at, gun) if at else None,
        entry=scan.entry if scan else None,  # type: ignore[arg-type]
        device_id=scan.device_id if scan else None,
    )


async def runner_times(session: AsyncSession, bib: str) -> RunnerTimesOut:
    runner, category = await _runner(session, bib)
    checkpoints = list(
        await session.scalars(
            select(Checkpoint)
            .where(Checkpoint.route_id == category.route_id)
            .order_by(Checkpoint.distance_km)
        )
    )
    scans = {
        s.checkpoint_id: s
        for s in await session.scalars(select(Scan).where(Scan.runner_id == runner.id))
    }
    names = {cp.id: cp.name for cp in checkpoints}
    history = [
        Correction(
            action=c.action,  # type: ignore[arg-type]
            checkpoint_id=c.checkpoint_id,
            checkpoint_name=names.get(c.checkpoint_id, str(c.checkpoint_id)),
            previous=c.previous,
            new=c.new,
            reason=c.reason,
            admin_name=c.admin_name,
            created_at=c.created_at,
        )
        for c in await session.scalars(
            select(ScanCorrection)
            .where(ScanCorrection.runner_id == runner.id)
            .order_by(ScanCorrection.created_at.desc(), ScanCorrection.id.desc())
        )
    ]
    standings = await timing.compute_standings(session, category)
    status = next((s.status for s in standings if s.bib_number == runner.bib_number), "registered")
    await session.commit()  # release the row lock taken while reading
    return RunnerTimesOut(
        bib_number=runner.bib_number,
        full_name=f"{runner.first_name} {runner.last_name}",
        category_code=category.code,
        status=status,
        checkpoints=[_time(cp, scans.get(cp.id), category.gun_start_at) for cp in checkpoints],
        history=history,
    )


def _who(admin: AdminUser | None) -> tuple[int | None, str]:
    return (admin.id, admin.name) if admin else (None, "Development token")


async def _announce(
    redis: Redis, runner: Runner, category: Category, checkpoint: Checkpoint, at: datetime
) -> None:
    try:
        await timing.mark_changed(redis, {category.id})
        event = ScanEvent(
            bib_number=runner.bib_number,
            category_code=category.code,
            checkpoint_id=checkpoint.id,
            checkpoint_name=checkpoint.name,
            distance_km=float(checkpoint.distance_km),
            scanned_at=at,
            elapsed_seconds=timing.elapsed(at, category.gun_start_at),
        )
        await publish(redis, SCANS_CHANNEL, event.model_dump(mode="json"))
    except Exception as exc:  # the change is saved; live updates are best effort
        log.warning("Correction saved, but live updates failed: %s", exc)


async def set_time(
    session: AsyncSession,
    redis: Redis,
    admin: AdminUser | None,
    bib: str,
    checkpoint_id: int,
    scanned_at: datetime,
    reason: str,
) -> ChangeOut:
    if scanned_at > datetime.now(UTC) + MAX_FUTURE:
        raise AppError(
            422, "TIME_IN_FUTURE", "That time is in the future. Check the date and time."
        )
    runner, category = await _runner(session, bib)
    checkpoint = await _checkpoint(session, category, checkpoint_id)
    scan = await session.scalar(
        select(Scan)
        .where(Scan.runner_id == runner.id, Scan.checkpoint_id == checkpoint.id)
        .with_for_update()
    )
    admin_id, admin_name = _who(admin)
    previous = _snapshot(scan) if scan else None
    if scan is None:
        scan = Scan(client_id=uuid.uuid4(), runner_id=runner.id, checkpoint_id=checkpoint.id,
                    device_id=f"office:{admin_id or 'dev'}", scanned_at=scanned_at)  # fmt: skip
        session.add(scan)
    scan.scanned_at = scanned_at
    scan.clock_offset_ms = 0  # the office's time is the true time
    scan.entry = "office"
    scan.device_id = f"office:{admin_id or 'dev'}"
    scan.received_at = datetime.now(UTC)
    await session.flush()
    action = "correct" if previous else "add"
    session.add(
        ScanCorrection(
            runner_id=runner.id,
            checkpoint_id=checkpoint.id,
            action=action,
            previous=previous,
            new=_snapshot(scan),
            reason=reason.strip(),
            admin_id=admin_id,
            admin_name=admin_name,
        )
    )
    await session.commit()
    await _announce(redis, runner, category, checkpoint, scanned_at)
    return ChangeOut(action=action, checkpoint=_time(checkpoint, scan, category.gun_start_at))  # type: ignore[arg-type]


async def remove_time(
    session: AsyncSession,
    redis: Redis,
    admin: AdminUser | None,
    bib: str,
    checkpoint_id: int,
    reason: str,
) -> ChangeOut:
    runner, category = await _runner(session, bib)
    checkpoint = await _checkpoint(session, category, checkpoint_id)
    scan = await session.scalar(
        select(Scan)
        .where(Scan.runner_id == runner.id, Scan.checkpoint_id == checkpoint.id)
        .with_for_update()
    )
    if scan is None:
        raise AppError(
            404, "SCAN_NOT_FOUND", f"{runner.bib_number} has no time at {checkpoint.name}."
        )
    admin_id, admin_name = _who(admin)
    session.add(
        ScanCorrection(
            runner_id=runner.id,
            checkpoint_id=checkpoint.id,
            action="remove",
            previous=_snapshot(scan),
            new=None,
            reason=reason.strip(),
            admin_id=admin_id,
            admin_name=admin_name,
        )
    )
    await session.delete(scan)
    await session.commit()
    try:
        await timing.mark_changed(redis, {category.id})
    except Exception as exc:
        log.warning("Removal saved, but the leaderboard refresh failed: %s", exc)
    return ChangeOut(action="remove", checkpoint=_time(checkpoint, None, category.gun_start_at))
