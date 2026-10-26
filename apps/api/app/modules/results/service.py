"""Results and the live scan stream. Routers call this; it never imports FastAPI.

GET /results reads the timing engine (E9); /stream/results relays the `scans`
Redis channel that scan ingestion publishes to (E11).
"""

from collections.abc import AsyncIterator

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.broadcast import broadcaster
from app.models import Category
from app.modules.results.schemas import SCANS_CHANNEL, ResultItem, ResultsPage, ScanEvent
from app.modules.timing import service as timing


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


async def scan_events(redis: Redis, category: str | None) -> AsyncIterator[ScanEvent]:
    """Every saved scan, as it happens (published by scan ingestion), optionally one race only."""
    code = category.upper() if category else None
    async with broadcaster(redis, SCANS_CHANNEL).listen(SCANS_CHANNEL) as messages:
        async for data in messages:
            event = ScanEvent.model_validate(data)
            if code is None or event.category_code == code:
                yield event
