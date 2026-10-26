"""GPS tracking endpoints. Owner: Lead (E13 ingestion, E14 live positions)."""

from collections.abc import AsyncIterable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.core.deps import GatewayDep, SessionDep
from app.core.redis import RedisDep
from app.core.schemas import error_responses
from app.modules.gps import ingest, live, service
from app.modules.gps.schemas import GpsBatchAccepted, GpsBatchIn, PositionsSnapshot

router = APIRouter(tags=["gps"])


async def _bib(
    bib: Annotated[str, Query(description="Bib number, e.g. F0001")], session: SessionDep
) -> str:
    # A dependency runs before streaming starts, so a 404 is still a normal response.
    return await service.runner_bib(session, bib)


@router.post(
    "/gps/positions",
    status_code=202,
    dependencies=[GatewayDep],
    responses=error_responses(401),
)
async def ingest_positions(body: GpsBatchIn, redis: RedisDep) -> GpsBatchAccepted:
    """GPS gateway only (`X-Gateway-Secret`). Points are queued and saved within a second
    or two; unknown or unassigned trackers are dropped then."""
    return GpsBatchAccepted(accepted=await ingest.queue_positions(redis, body.positions))


@router.post(
    "/gps/traccar",
    status_code=202,
    dependencies=[GatewayDep],
    responses=error_responses(401),
)
async def ingest_traccar(payload: dict[str, Any], redis: RedisDep) -> GpsBatchAccepted:
    """Traccar's own JSON forwarding (`forward.type=json`): one position per request.

    Point Traccar's `forward.url` here, with the secret in an `X-Gateway-Secret`
    header (`forward.header`) or as `?secret=` in the URL.
    """
    position = ingest.from_traccar(payload)
    queued = await ingest.queue_positions(redis, [position]) if position else 0
    return GpsBatchAccepted(accepted=queued)


@router.get("/positions")
async def positions(
    session: SessionDep,
    redis: RedisDep,
    category: Annotated[str | None, Query(description="Category code, e.g. FULL")] = None,
) -> PositionsSnapshot:
    """Latest point of every runner on course (finishers and DNF excluded). Poll every 5 s:
    the snapshot is rebuilt at most that often and served from a cache."""
    return await live.snapshot(session, redis, category)


@router.get(
    "/stream/positions",
    response_class=EventSourceResponse,
    responses=error_responses(404),
)
async def stream_positions(
    bib: Annotated[str, Depends(_bib)], session: SessionDep, redis: RedisDep
) -> AsyncIterable[ServerSentEvent]:
    """Server-Sent Events for one runner: `event: position` with the current position
    straight away, then on every new fix. A `: ping` comment every 15 s."""
    async for event in service.position_events(session, redis, bib):
        yield ServerSentEvent(event="position", data=event)
