"""Database and business logic for GPS tracking. Routers call this; it never imports FastAPI.

STUB(E13, E14): positions come from the fake race in app/stubs/race.py. Real
ingestion pushes to a Redis stream; real snapshots are served from Redis.
"""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from app.core.errors import AppError
from app.modules.gps.schemas import GpsBatchIn, PositionEvent, PositionsSnapshot, RunnerPosition
from app.stubs import race

STREAM_TICK_S = 5.0


async def ingest(body: GpsBatchIn) -> int:
    return len(body.positions)


async def snapshot(category: str | None) -> PositionsSnapshot:
    runners = []
    for r in race.runners():
        if category and r.category_code != category.upper():
            continue
        state = race.runner_state(r)
        live = state["live_position"]
        if state["status"] != "started" or live is None:
            continue  # only runners on course with a tracker
        runners.append(
            RunnerPosition(
                bib_number=r.bib_number,
                category_code=r.category_code,
                gender=r.gender,  # type: ignore[arg-type]
                lat=live["lat"],
                lng=live["lng"],
                distance_km=live["distance_km"],
                is_stale=live["is_stale"],
            )
        )
    return PositionsSnapshot(updated_at=datetime.now(UTC), runners=runners)


def check_runner(bib: str) -> race.FakeRunner:
    r = race.runner_by_bib(bib)
    if r is None:
        raise AppError(404, "RUNNER_NOT_FOUND", f"No runner with bib {bib.upper()}.")
    return r


async def position_events(r: race.FakeRunner) -> AsyncIterator[PositionEvent]:
    """Yield the runner's position on every new (fake) fix."""
    last_recorded = None
    while True:
        live = race.runner_state(r)["live_position"]
        if live is not None and live["recorded_at"] != last_recorded:
            last_recorded = live["recorded_at"]
            yield PositionEvent(bib_number=r.bib_number, **live)
        await asyncio.sleep(STREAM_TICK_S)
