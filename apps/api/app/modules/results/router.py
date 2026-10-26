"""results endpoints. Owner: Lead (E9, E11)."""

from collections.abc import AsyncIterable
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.core.deps import SessionDep
from app.core.redis import RedisDep
from app.modules.results import service
from app.modules.results.schemas import ResultsPage

router = APIRouter(tags=["results"])


@router.get("/results")
async def get_results(
    category: Annotated[str | None, Query(description="Category code, e.g. HALF")] = None,
    gender: Literal["M", "F"] | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    *,
    session: SessionDep,
    redis: RedisDep,
) -> ResultsPage:
    return await service.get_results(session, redis, category, gender, limit, offset)


@router.get("/stream/results", response_class=EventSourceResponse)
async def stream_results(
    redis: RedisDep,
    category: Annotated[
        str | None, Query(description="Only this race, e.g. HALF. Empty = every race.")
    ] = None,
) -> AsyncIterable[ServerSentEvent]:
    """Server-Sent Events: `event: scan` each time a runner is scanned at a checkpoint.

    A keep-alive comment is sent every 15 s when nothing else happens. Pages should
    re-fetch what they show (throttled) rather than patch it from the event.
    """
    async for scan in service.scan_events(redis, category):
        yield ServerSentEvent(event="scan", data=scan)
