"""Checkpoint scanner login and the offline runner list. Owner: Lead (E7).

A volunteer unlocks the scanner with the checkpoint's 6-digit PIN (made with
`python -m scripts.checkpoint_pins`). The phone gets a 24-hour token bound to
that checkpoint and downloads the names of every runner on its course, so it can
show "Ada Okafor, H0042" while offline.

Wrong PINs are limited to 10 per IP address per 15 minutes.
"""

from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.errors import AppError
from app.models import Category, Checkpoint, Runner
from app.modules.scanner.schemas import (
    CheckpointInfo,
    RosterOut,
    RosterRunner,
    ScannerLoginOut,
)

FAILED_PIN_LIMIT = 10
FAILED_PIN_WINDOW_S = 15 * 60


async def checkpoint_info(session: AsyncSession, checkpoint: Checkpoint) -> CheckpointInfo:
    codes = await session.scalars(
        select(Category.code)
        .where(Category.route_id == checkpoint.route_id)
        .order_by(Category.sort_order)
    )
    return CheckpointInfo(
        id=checkpoint.id,
        code=checkpoint.code,
        name=checkpoint.name,
        distance_km=float(checkpoint.distance_km),
        is_start=checkpoint.is_start,
        is_finish=checkpoint.is_finish,
        category_codes=list(codes),
    )


async def login(
    session: AsyncSession, redis: Redis, pin: str, device_id: str, client_ip: str
) -> ScannerLoginOut:
    failures_key = f"scanner:pin-failures:{client_ip}"
    if int(await redis.get(failures_key) or 0) >= FAILED_PIN_LIMIT:
        raise AppError(429, "PIN_RATE_LIMITED", "Too many wrong PINs. Wait 15 minutes.")

    checkpoint = await session.scalar(
        select(Checkpoint).where(Checkpoint.pin_hash == security.hash_pin(pin))
    )
    if checkpoint is None:
        async with redis.pipeline(transaction=True) as pipe:
            pipe.incr(failures_key)
            pipe.expire(failures_key, FAILED_PIN_WINDOW_S, nx=True)
            await pipe.execute()
        raise AppError(401, "PIN_INVALID", "That PIN is not correct.")

    now = datetime.now(UTC)
    return ScannerLoginOut(
        token=security.create_scanner_token(device_id, checkpoint.id, now),
        expires_at=now + security.SCANNER_TOKEN_TTL,
        checkpoint=await checkpoint_info(session, checkpoint),
    )


async def roster(session: AsyncSession, checkpoint_id: int) -> RosterOut:
    checkpoint = await session.get(Checkpoint, checkpoint_id)
    if checkpoint is None:
        raise AppError(401, "SCANNER_AUTH_REQUIRED", "This checkpoint no longer exists.")
    rows = await session.execute(
        select(Runner.id, Runner.bib_number, Runner.first_name, Runner.last_name, Category.code)
        .join(Category, Category.id == Runner.category_id)
        .where(Category.route_id == checkpoint.route_id)
        .order_by(Runner.bib_number)
    )
    return RosterOut(
        checkpoint_id=checkpoint.id,
        generated_at=datetime.now(UTC),
        runners=[
            RosterRunner(
                runner_id=rid, bib_number=bib, full_name=f"{first} {last}", category_code=code
            )
            for rid, bib, first, last, code in rows
        ],
    )
