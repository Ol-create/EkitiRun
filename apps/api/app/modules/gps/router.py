"""GPS tracking endpoints. Owner: Lead (E13, E14)."""

from collections.abc import AsyncIterable
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.core.deps import GatewayDep
from app.core.schemas import error_responses
from app.modules.gps import service
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
async def ingest_positions(body: GpsBatchIn) -> GpsBatchAccepted:
    """Traccar gateway only (`X-Gateway-Secret` header)."""
    return GpsBatchAccepted(accepted=await service.ingest(body))


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
