"""Saving checkpoint scans uploaded by scanner phones. Owner: Lead (E8).

Each scan in a batch gets its own answer:
- accepted: saved. If the runner was already scanned here, the EARLIEST scan
  wins (comparing clock-corrected times), so a later re-scan never moves a
  split, but an earlier scan from a slower-syncing phone does replace it.
- duplicate: nothing to do (a retried upload, or a later re-scan).
- invalid: bad_qr / unknown_bib / wrong_course.

Clock drift: the phone sends its own clock reading (`sent_at`) with each
upload. Server time minus that reading is stored on the device and on every
scan in the batch (`clock_offset_ms`), and phones off by more than 2 minutes
are flagged in GET /admin/scanner-devices.
"""

import logging
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import func, literal_column, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.broadcast import publish
from app.core.errors import AppError
from app.core.security import parse_qr_token
from app.models import Category, Checkpoint, Runner, Scan, ScannerDevice
from app.models.scanner_device import CLOCK_TOLERANCE_MS
from app.modules.results.schemas import SCANS_CHANNEL, ScanEvent
from app.modules.scans.schemas import InvalidReason, ScanBatchIn, ScanBatchOut, ScanIn, ScanResult
from app.modules.timing import service as timing

log = logging.getLogger("ekitirun.scans")
TYPED_BIB = re.compile(r"^([A-Z])\s*0*(\d{1,4})$")


def _typed_bib(raw: str) -> str | None:
    match = TYPED_BIB.match(raw.strip().upper())
    return f"{match[1]}{int(match[2]):04d}" if match else None


async def _record_device(
    session: AsyncSession, device_id: str, checkpoint_id: int, offset_ms: int | None, count: int
) -> None:
    stmt = insert(ScannerDevice).values(
        device_id=device_id,
        checkpoint_id=checkpoint_id,
        last_seen_at=func.now(),
        clock_offset_ms=offset_ms,
        scans_uploaded=count,
    )
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=[ScannerDevice.device_id],
            set_={
                "checkpoint_id": stmt.excluded.checkpoint_id,
                "last_seen_at": stmt.excluded.last_seen_at,
                # keep the last known offset if this upload didn't send one
                "clock_offset_ms": func.coalesce(
                    stmt.excluded.clock_offset_ms, ScannerDevice.clock_offset_ms
                ),
                "scans_uploaded": ScannerDevice.scans_uploaded + stmt.excluded.scans_uploaded,
            },
        )
    )
    if offset_ms is not None and abs(offset_ms) > CLOCK_TOLERANCE_MS:
        log.warning(
            "Scanner %s at checkpoint %s: clock is off by %.0f s",
            device_id, checkpoint_id, offset_ms / 1000,
        )  # fmt: skip


def _corrected(table: Any) -> ColumnElement[datetime]:
    """scanned_at + clock offset, as a SQL expression (offset 0 when unknown)."""
    return table.scanned_at + func.coalesce(table.clock_offset_ms, 0) * text(
        "interval '1 millisecond'"
    )


async def _save(
    session: AsyncSession,
    scan: ScanIn,
    runner_id: uuid.UUID,
    checkpoint_id: int,
    device_id: str,
    offset_ms: int | None,
) -> bool:
    """Insert, or replace a later scan of this runner here. True if saved."""
    stmt = insert(Scan).values(
        id=uuid.uuid4(),
        client_id=scan.client_id,
        runner_id=runner_id,
        checkpoint_id=checkpoint_id,
        device_id=device_id,
        scanned_at=scan.scanned_at,
        clock_offset_ms=offset_ms,
        entry=scan.entry,
    )
    upsert: Any = stmt.on_conflict_do_update(
        constraint="uq_scans_runner_checkpoint",
        set_={
            "client_id": stmt.excluded.client_id,
            "device_id": stmt.excluded.device_id,
            "scanned_at": stmt.excluded.scanned_at,
            "clock_offset_ms": stmt.excluded.clock_offset_ms,
            "entry": stmt.excluded.entry,
            "received_at": func.now(),
        },
        where=_corrected(stmt.excluded) < _corrected(Scan.__table__.c),
    ).returning(literal_column("1"))
    try:
        async with session.begin_nested():  # a clash on client_id only undoes this scan
            return (await session.execute(upsert)).first() is not None
    except IntegrityError:
        return False  # the same client_id arrived twice at once: a retry


async def _publish(
    session: AsyncSession,
    redis: Redis,
    checkpoint: Checkpoint,
    saved: list[tuple[str, int, ScanIn]],
    offset_ms: int | None,
) -> None:
    """Announce saved scans on the `scans` channel (GET /stream/results, E11)."""
    if not saved:
        return
    categories = {
        c.id: c
        for c in await session.scalars(
            select(Category).where(Category.id.in_({cid for _, cid, _ in saved}))
        )
    }
    for bib, category_id, scan in saved:
        category = categories[category_id]
        at = scan.scanned_at + timedelta(milliseconds=offset_ms or 0)
        event = ScanEvent(
            bib_number=bib,
            category_code=category.code,
            checkpoint_id=checkpoint.id,
            checkpoint_name=checkpoint.name,
            distance_km=float(checkpoint.distance_km),
            scanned_at=at,
            elapsed_seconds=timing.elapsed(at, category.gun_start_at),
        )
        try:
            await publish(redis, SCANS_CHANNEL, event.model_dump(mode="json"))
        except Exception as exc:  # live updates are a bonus: never fail the upload for them
            log.warning("Couldn't publish scan of %s: %s", bib, exc)


async def ingest_batch(
    session: AsyncSession, redis: Redis, device_id: str, body: ScanBatchIn
) -> ScanBatchOut:
    checkpoint = await session.get(Checkpoint, body.checkpoint_id)
    if checkpoint is None:
        raise AppError(401, "SCANNER_AUTH_REQUIRED", "This checkpoint no longer exists.")

    offset_ms = None
    if body.sent_at is not None:
        offset_ms = round((datetime.now(UTC) - body.sent_at).total_seconds() * 1000)
    await _record_device(session, device_id, checkpoint.id, offset_ms, len(body.scans))

    # Work out which runner each scan is for.
    wanted: list[tuple[ScanIn, uuid.UUID | None, str | None, InvalidReason | None]] = []
    for scan in body.scans:
        if scan.entry == "qr":
            try:
                token_runner_id, token_bib = parse_qr_token(scan.qr_token)
                wanted.append((scan, token_runner_id, token_bib, None))
            except AppError:
                wanted.append((scan, None, None, "bad_qr"))
        else:
            typed = _typed_bib(scan.qr_token)
            wanted.append((scan, None, typed, None if typed else "unknown_bib"))

    bibs = {bib for _, _, bib, reason in wanted if bib and not reason}
    runners = {
        bib: (rid, route_id, category_id)
        for rid, bib, route_id, category_id in await session.execute(
            select(Runner.id, Runner.bib_number, Category.route_id, Category.id)
            .join(Category, Category.id == Runner.category_id)
            .where(Runner.bib_number.in_(bibs))
        )
    }
    already = set(
        await session.scalars(
            select(Scan.client_id).where(Scan.client_id.in_([s.client_id for s in body.scans]))
        )
    )

    results = []
    changed_categories: set[int] = set()
    saved_scans: list[tuple[str, int, ScanIn]] = []  # (bib, category id, scan) for live events
    for scan, qr_runner_id, bib, reason in wanted:
        found = runners.get(bib) if bib else None
        if reason is None and (found is None or (qr_runner_id and found[0] != qr_runner_id)):
            reason = "unknown_bib"
        if reason is None and found and found[1] != checkpoint.route_id:
            reason = "wrong_course"
        if reason is not None or found is None:
            results.append(
                ScanResult(
                    client_id=scan.client_id, status="invalid", bib_number=bib, reason=reason
                )
            )
            continue
        if scan.client_id in already:
            saved = False
        else:
            saved = await _save(session, scan, found[0], checkpoint.id, device_id, offset_ms)
        if saved and bib:
            changed_categories.add(found[2])
            saved_scans.append((bib, found[2], scan))
        results.append(
            ScanResult(
                client_id=scan.client_id,
                status="accepted" if saved else "duplicate",
                bib_number=bib,
            )
        )

    await session.commit()
    await timing.mark_changed(redis, changed_categories)  # standings rebuild on next read
    await _publish(session, redis, checkpoint, saved_scans, offset_ms)
    return ScanBatchOut(results=results)
