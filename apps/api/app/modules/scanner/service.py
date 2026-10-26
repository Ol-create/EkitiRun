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
from app.models import Category, Checkpoint, Runner, ScannerDevice
from app.modules.scanner.schemas import (
    CheckpointInfo,
    RosterOut,
    RosterRunner,
    ScannerDeviceOut,
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


async def check_pin_attempts(redis: Redis, client_ip: str) -> None:
    """429 after 10 wrong PINs (scanner or kit desk) from this IP in 15 minutes."""
    if int(await redis.get(f"scanner:pin-failures:{client_ip}") or 0) >= FAILED_PIN_LIMIT:
        raise AppError(429, "PIN_RATE_LIMITED", "Too many wrong PINs. Wait 15 minutes.")


async def record_wrong_pin(redis: Redis, client_ip: str) -> None:
    failures_key = f"scanner:pin-failures:{client_ip}"
    async with redis.pipeline(transaction=True) as pipe:
        pipe.incr(failures_key)
        pipe.expire(failures_key, FAILED_PIN_WINDOW_S, nx=True)
        await pipe.execute()


async def login(
    session: AsyncSession, redis: Redis, pin: str, device_id: str, client_ip: str
) -> ScannerLoginOut:
    await check_pin_attempts(redis, client_ip)

    checkpoint = await session.scalar(
        select(Checkpoint).where(Checkpoint.pin_hash == security.hash_pin(pin))
    )
    if checkpoint is None:
        await record_wrong_pin(redis, client_ip)
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


async def list_devices(session: AsyncSession) -> list[ScannerDeviceOut]:
    """Every phone that has uploaded scans, flagged clocks first, then most recent."""
    rows = (
        await session.execute(
            select(ScannerDevice, Checkpoint).join(
                Checkpoint, Checkpoint.id == ScannerDevice.checkpoint_id
            )
        )
    ).all()
    out = []
    for device, checkpoint in rows:
        info = await checkpoint_info(session, checkpoint)
        out.append(
            ScannerDeviceOut(
                device_id=device.device_id,
                checkpoint_id=checkpoint.id,
                checkpoint_name=checkpoint.name,
                category_codes=info.category_codes,
                first_seen_at=device.first_seen_at,
                last_seen_at=device.last_seen_at,
                scans_uploaded=device.scans_uploaded,
                clock_offset_s=None
                if device.clock_offset_ms is None
                else round(device.clock_offset_ms / 1000, 1),
                clock_flagged=device.clock_flagged,
            )
        )
    return sorted(out, key=lambda d: (not d.clock_flagged, -d.last_seen_at.timestamp()))
