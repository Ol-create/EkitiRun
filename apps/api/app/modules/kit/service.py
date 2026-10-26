"""Kit collection and tracker returns. Owner: Lead (E15).

A kit-desk volunteer scans the runner's QR, then the tracker's label, and the two
are linked: from then on that tracker's GPS points belong to that runner (the
GPS writer picks the change up within 30 s). At the finish, scanning the tracker
returns it. Deposits and bib-collection rules are the organisers' call: this
only records hand-outs and returns.

Both rows are locked while linking, so two desks can never hand out the same
tracker, or give one runner two trackers.
"""

import re
from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import cast

from redis.asyncio import Redis
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import (
    SCANNER_TOKEN_TTL,
    create_kit_token,
    kit_pin_matches,
    parse_qr_token,
)
from app.models import Category, Runner, Tracker
from app.modules.gps.live import LIVE_KEY
from app.modules.kit.schemas import (
    KitAssignIn,
    KitAssignOut,
    KitLoginOut,
    KitReturnOut,
    OutstandingOut,
    OutstandingTracker,
)
from app.modules.scanner.service import check_pin_attempts, record_wrong_pin
from app.modules.timing import service as timing

TYPED_BIB = re.compile(r"^([A-Z])\s*0*(\d{1,4})$")
LABEL = re.compile(r"TRK-?0*(\d{1,4})")


async def login(redis: Redis, pin: str, device_id: str, client_ip: str) -> KitLoginOut:
    await check_pin_attempts(redis, client_ip)
    if not kit_pin_matches(pin):
        await record_wrong_pin(redis, client_ip)
        raise AppError(401, "PIN_INVALID", "That PIN is not correct.")
    now = datetime.now(UTC)
    return KitLoginOut(token=create_kit_token(device_id, now), expires_at=now + SCANNER_TOKEN_TTL)


def tracker_key(raw: str) -> str:
    """'trk-0031', ' 31 ' and 'TRK-0031' all mean TRK-0031; anything else is a device number."""
    text = raw.strip().upper()
    if text.isdigit() and len(text) <= 4:
        return f"TRK-{int(text):04d}"
    match = LABEL.fullmatch(text)
    return f"TRK-{int(match[1]):04d}" if match else text


async def _tracker(session: AsyncSession, raw: str) -> Tracker:
    key = tracker_key(raw)
    tracker = await session.scalar(
        select(Tracker)
        .where(or_(Tracker.label == key, Tracker.device_id == raw.strip()))
        .with_for_update()
    )
    if tracker is None:
        raise AppError(404, "TRACKER_NOT_FOUND", f"No tracker {key}. Check the label.")
    return tracker


async def _runner(session: AsyncSession, body: KitAssignIn) -> Runner:
    if body.qr_token is not None:
        runner_id, bib = parse_qr_token(body.qr_token)  # 400 QR_INVALID if edited or damaged
        query = select(Runner).where(Runner.id == runner_id, Runner.bib_number == bib)
    else:
        typed = (body.bib_number or "").strip().upper()
        match = TYPED_BIB.match(typed)
        bib = f"{match[1]}{int(match[2]):04d}" if match else typed
        query = select(Runner).where(Runner.bib_number == bib)
    runner = await session.scalar(query.with_for_update())
    if runner is None:
        raise AppError(404, "RUNNER_NOT_FOUND", "No registered runner for that bib.")
    return runner


def _name(runner: Runner) -> str:
    return f"{runner.first_name} {runner.last_name}"


async def assign(session: AsyncSession, body: KitAssignIn) -> KitAssignOut:
    runner = await _runner(session, body)
    tracker = await _tracker(session, body.tracker_label)
    category = await session.get(Category, runner.category_id)
    assert category is not None
    out = KitAssignOut(
        bib_number=runner.bib_number,
        full_name=_name(runner),
        category_code=category.code,
        tracker_label=tracker.label,
    )

    if tracker.runner_id == runner.id:
        await session.commit()
        return out.model_copy(update={"already_assigned": True})
    if tracker.status == "lost":
        raise AppError(409, "TRACKER_LOST", f"{tracker.label} is marked lost. Use another one.")
    if tracker.status == "assigned":
        holder = await session.get(Runner, tracker.runner_id)
        who = holder.bib_number if holder else "another runner"
        raise AppError(409, "TRACKER_IN_USE", f"{tracker.label} is already with {who}.")
    current = await session.scalar(select(Tracker.label).where(Tracker.runner_id == runner.id))
    if current is not None:
        raise AppError(
            409,
            "RUNNER_HAS_TRACKER",
            f"{runner.bib_number} already has {current}. Return it first.",
        )

    now = datetime.now(UTC)
    tracker.status, tracker.runner_id, tracker.assigned_at = "assigned", runner.id, now
    tracker.returned_at = None
    runner.kit_collected_at = runner.kit_collected_at or now
    await session.commit()
    return out


async def return_tracker(session: AsyncSession, redis: Redis, raw_label: str) -> KitReturnOut:
    tracker = await _tracker(session, raw_label)
    if tracker.status != "assigned" or tracker.runner_id is None:
        status = tracker.status
        await session.commit()
        raise AppError(
            409, "TRACKER_NOT_ASSIGNED", f"{tracker.label} isn't out with a runner ({status})."
        )
    runner = await session.get(Runner, tracker.runner_id)
    assert runner is not None
    tracker.status, tracker.runner_id, tracker.returned_at = "returned", None, datetime.now(UTC)
    await session.commit()
    # Take the runner's dot off the live map.
    await cast(Awaitable[int], redis.hdel(LIVE_KEY, str(runner.id)))
    return KitReturnOut(
        bib_number=runner.bib_number, full_name=_name(runner), tracker_label=tracker.label
    )


async def outstanding(session: AsyncSession, redis: Redis) -> OutstandingOut:
    """Trackers still out, with each runner's race status (finishers should return theirs)."""
    rows = (
        await session.execute(
            select(Tracker, Runner, Category)
            .join(Runner, Runner.id == Tracker.runner_id)
            .join(Category, Category.id == Runner.category_id)
            .where(Tracker.status == "assigned")
            .order_by(Runner.bib_number)
        )
    ).all()
    status_by_bib: dict[str, str] = {}
    for category in {c.id: c for _, _, c in rows}.values():
        for s in await timing.standings(session, redis, category):
            status_by_bib[s.bib_number] = s.status
    trackers = [
        OutstandingTracker(
            tracker_label=tracker.label,
            bib_number=runner.bib_number,
            full_name=_name(runner),
            category_code=category.code,
            race_status=status_by_bib.get(runner.bib_number, "registered"),  # type: ignore[arg-type]
            assigned_at=tracker.assigned_at,
        )
        for tracker, runner, category in rows
    ]
    return OutstandingOut(out=len(trackers), trackers=trackers)
