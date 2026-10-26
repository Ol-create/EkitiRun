"""GPS endpoints' logic. Routers call this; it never imports FastAPI. Owner: Lead (E13, E14).

Ingestion: app/modules/gps/ingest.py. Live positions: app/modules/gps/live.py.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.broadcast import broadcaster
from app.core.errors import AppError
from app.models import Runner
from app.modules.gps import live
from app.modules.gps.schemas import PositionEvent


async def runner_bib(session: AsyncSession, bib: str) -> str:
    """The runner's bib in its official form, or 404 RUNNER_NOT_FOUND."""
    found = await session.scalar(select(Runner.bib_number).where(Runner.bib_number == bib.upper()))
    if found is None:
        raise AppError(404, "RUNNER_NOT_FOUND", f"No runner with bib {bib.upper()}.")
    return found


async def position_events(
    session: AsyncSession, redis: Redis, bib: str
) -> AsyncIterator[PositionEvent]:
    """The runner's current position straight away (if any), then every new fix."""
    runner_id = await session.scalar(select(Runner.id).where(Runner.bib_number == bib))
    async with broadcaster(redis, "positions:*").listen(live.channel(bib)) as messages:
        current = await live.get_live_position(redis, runner_id)
        if current is not None:
            yield PositionEvent(bib_number=bib, **current.model_dump())
        await session.close()  # don't hold a database connection for the whole stream
        async for data in messages:
            event = PositionEvent.model_validate(data)
            age = (datetime.now(UTC) - event.recorded_at).total_seconds()
            event.is_stale = age > live.STALE_AFTER_S
            yield event
