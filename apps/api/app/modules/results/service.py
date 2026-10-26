"""Results and the live scan stream. Routers call this; it never imports FastAPI.

GET /results reads the timing engine (E9).
STUB(E11): the scan stream still replays the fake race in app/stubs/race.py.
"""

import asyncio
from collections.abc import AsyncIterator

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category
from app.modules.results.schemas import ResultItem, ResultsPage, ScanEvent
from app.modules.timing import service as timing
from app.stubs import race

STREAM_TICK_S = 3.0


async def get_results(
    session: AsyncSession,
    redis: Redis,
    category: str | None,
    gender: str | None,
    limit: int,
    offset: int,
) -> ResultsPage:
    """Leaderboard from the timing engine (E9). Without a category: every race, in order.

    `position` is the place in the race, or among the runner's gender when
    filtering by gender.
    """
    query = select(Category).order_by(Category.sort_order, Category.id)
    if category:
        query = query.where(Category.code == category.upper())
    rows: list[ResultItem] = []
    for cat in await session.scalars(query):
        for s in await timing.standings(session, redis, cat):
            if gender and s.gender != gender:
                continue
            rows.append(
                ResultItem(
                    position=s.position_gender if gender else s.position,
                    bib_number=s.bib_number,
                    full_name=s.full_name,
                    gender=s.gender,  # type: ignore[arg-type]
                    category_code=s.category_code,
                    status=s.status,  # type: ignore[arg-type]
                    last_checkpoint=s.last_checkpoint,
                    elapsed_seconds=s.elapsed_seconds,
                    finish_seconds=s.finish_seconds,
                )
            )
    return ResultsPage(items=rows[offset : offset + limit], total=len(rows))


async def scan_events() -> AsyncIterator[ScanEvent]:
    """Yield a scan event whenever a fake runner passes a checkpoint."""
    previous = race.race_elapsed_s()
    while True:
        await asyncio.sleep(STREAM_TICK_S)
        now = race.race_elapsed_s()
        if now < previous:  # the fake race clock looped back to the start
            previous = 0.0
        for r in race.runners():
            for split in race.runner_state(r, now)["splits"]:
                if previous < split["elapsed_seconds"] <= now:
                    yield ScanEvent(
                        bib_number=r.bib_number,
                        checkpoint_id=split["checkpoint_id"],
                        elapsed_seconds=split["elapsed_seconds"],
                    )
        previous = now
