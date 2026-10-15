"""Logic for the tracker inventory. Routers call this; it never imports FastAPI.

STUB(B5): a fixed fake inventory of 40 trackers; nothing is saved.
"""

from datetime import UTC, datetime, timedelta
from functools import cache

from app.core.errors import AppError
from app.modules.trackers.schemas import TrackerIn, TrackerOut, TrackerPatch
from app.stubs import race


@cache
def _inventory() -> list[TrackerOut]:
    bibs = [r.bib_number for r in race.runners() if r.has_tracker][:30]
    now = datetime.now(UTC)
    out = []
    for i in range(1, 41):
        status = "assigned" if i <= 30 else "lost" if i == 40 else "available"
        out.append(
            TrackerOut(
                id=i,
                device_id=f"86{i:013d}",
                label=f"TRK-{i:04d}",
                status=status,  # type: ignore[arg-type]
                bib_number=bibs[i - 1] if status == "assigned" else None,
                battery_pct=100 - (i * 7) % 60 if status == "assigned" else None,
                last_seen_at=now - timedelta(seconds=i * 13) if status == "assigned" else None,
            )
        )
    return out


def find_by_label(label: str) -> TrackerOut | None:
    return next((t for t in _inventory() if t.label == label.upper()), None)


async def list_trackers(status: str | None) -> list[TrackerOut]:
    return [t for t in _inventory() if status is None or t.status == status]


async def create_tracker(body: TrackerIn) -> TrackerOut:
    if any(t.device_id == body.device_id or t.label == body.label.upper() for t in _inventory()):
        raise AppError(409, "TRACKER_EXISTS", "A tracker with that device id or label exists.")
    return TrackerOut(
        id=len(_inventory()) + 1,
        device_id=body.device_id,
        label=body.label.upper(),
        status="available",
    )


async def update_tracker(tracker_id: int, body: TrackerPatch) -> TrackerOut:
    tracker = next((t for t in _inventory() if t.id == tracker_id), None)
    if tracker is None:
        raise AppError(404, "TRACKER_NOT_FOUND", "No tracker with that id.")
    return tracker.model_copy(update=body.model_dump(exclude_unset=True))
