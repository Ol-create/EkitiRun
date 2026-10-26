"""GPS tracking endpoints. Owner: Lead (E13 ingestion, E14 live positions)."""

from collections.abc import AsyncIterable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.core.deps import GatewayDep
from app.core.redis import RedisDep
from app.core.schemas import error_responses
from app.modules.gps import ingest, service
from app.modules.gps.schemas import GpsBatchAccepted, GpsBatchIn, PositionsSnapshot
from app.stubs import race

router = APIRouter(tags=["gps"])


def _runner_for_bib(
    bib: Annotated[str, Query(description="Bib number, e.g. F0001")],
) -> race.FakeRunner:
    # A dependency runs before streaming starts, so a 404 is still a normal response.
    return service.check_runner(bib)


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
    category: Annotated[str | None, Query(description="Category code, e.g. FULL")] = None,
) -> PositionsSnapshot:
    """Latest point for every runner on course. Poll every 5 s."""
    return await service.snapshot(category)


@router.get(
    "/stream/positions",
    response_class=EventSourceResponse,
    responses=error_responses(404),
)
async def stream_positions(
    runner: Annotated[race.FakeRunner, Depends(_runner_for_bib)],
) -> AsyncIterable[ServerSentEvent]:
    """Server-Sent Events for one runner: `event: position` on every new fix."""
    async for event in service.position_events(runner):
        yield ServerSentEvent(event="position", data=event)
