"""GPS ingestion: queue fast, write in bulk. Owner: Lead (E13).

    trackers -> Traccar -> POST /gps/positions -> Redis stream "gps:positions"
                                                     -> GPS writer (app/workers/gps_writer.py)
                                                     -> Postgres gps_positions

The API only validates and queues, so it answers in milliseconds even with every
runner reporting every 5 s (about 1,000 points per second). The writer reads the
stream in batches, drops points from unknown or unassigned trackers, places each
point on the runner's course, and inserts the batch in one statement. A point is
acknowledged only after it is saved, so a writer crash loses nothing.
"""

import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.geo import RouteGeometry
from app.models import Category, GpsPosition, Route, Runner, Tracker
from app.modules.gps.schemas import GpsPositionIn

log = logging.getLogger("ekitirun.gps")

STREAM = "gps:positions"
GROUP = "gps-writers"
STREAM_MAX_LEN = 2_000_000  # about half an hour of race-day traffic, if the writer stalls
OFF_ROUTE_M = 200.0
DEVICE_REFRESH_S = 30.0


# ---------------------------------------------------------------- API side


async def queue_positions(redis: Redis, positions: list[GpsPositionIn]) -> int:
    """Put points on the stream. Returns how many were queued."""
    if not positions:
        return 0
    async with redis.pipeline(transaction=False) as pipe:
        for p in positions:
            pipe.xadd(
                STREAM,
                {"p": p.model_dump_json()},
                maxlen=STREAM_MAX_LEN,
                approximate=True,
            )
        await pipe.execute()
    return len(positions)


def from_traccar(payload: dict[str, Any]) -> GpsPositionIn | None:
    """One position from Traccar's JSON forwarding (`forward.type=json`).

    Traccar sends `{"position": {...}, "device": {"uniqueId": ...}}`. Returns None
    for anything without a device id, coordinates and a fix time.
    """
    position = payload.get("position") or {}
    device = payload.get("device") or {}
    attributes = position.get("attributes") or {}
    device_id = device.get("uniqueId")
    fix_time = position.get("fixTime") or position.get("deviceTime")
    if not device_id or position.get("latitude") is None or not fix_time:
        return None
    battery = attributes.get("batteryLevel")
    return GpsPositionIn(
        device_id=str(device_id),
        lat=float(position["latitude"]),
        lng=float(position["longitude"]),
        accuracy_m=float(position["accuracy"]) if position.get("accuracy") else None,
        battery_pct=max(0, min(100, int(battery))) if battery is not None else None,
        recorded_at=fix_time,
    )


# ---------------------------------------------------------------- writer side


@dataclass(frozen=True)
class AssignedTracker:
    tracker_id: int
    runner_id: Any
    course: RouteGeometry


class TrackerIndex:
    """Which runner (and course) each device id belongs to, refreshed every 30 s."""

    def __init__(self) -> None:
        self.by_device: dict[str, AssignedTracker] = {}
        self.loaded_at = 0.0
        self._courses: dict[int, RouteGeometry] = {}

    async def refresh(self, session: AsyncSession, force: bool = False) -> None:
        if not force and time.monotonic() - self.loaded_at < DEVICE_REFRESH_S:
            return
        rows = await session.execute(
            select(Tracker.device_id, Tracker.id, Tracker.runner_id, Route.id, Route.geojson)
            .join(Runner, Runner.id == Tracker.runner_id)
            .join(Category, Category.id == Runner.category_id)
            .join(Route, Route.id == Category.route_id)
            .where(Tracker.status == "assigned")
        )
        index = {}
        for device_id, tracker_id, runner_id, route_id, geojson in rows:
            if route_id not in self._courses:
                coords = [(float(x), float(y)) for x, y in geojson["coordinates"]]
                self._courses[route_id] = RouteGeometry(coords)
            index[device_id] = AssignedTracker(tracker_id, runner_id, self._courses[route_id])
        self.by_device = index
        self.loaded_at = time.monotonic()


@dataclass
class WriteStats:
    saved: int = 0
    off_route: int = 0
    ignored: int = 0


async def write_batch(
    session: AsyncSession, trackers: TrackerIndex, positions: list[GpsPositionIn]
) -> WriteStats:
    """Save the points from assigned trackers in one insert. Commits."""
    await trackers.refresh(session)
    stats = WriteStats()
    rows: list[dict[str, Any]] = []
    latest: dict[int, tuple[datetime, int | None]] = {}
    for p in positions:
        assigned = trackers.by_device.get(p.device_id)
        if assigned is None:
            stats.ignored += 1  # unknown, available, returned or lost tracker
            continue
        placed = assigned.course.place(p.lat, p.lng)
        off = placed.off_route_m > OFF_ROUTE_M
        stats.saved += 1
        stats.off_route += off
        rows.append(
            {
                "tracker_id": assigned.tracker_id,
                "runner_id": assigned.runner_id,
                "lat": p.lat,
                "lng": p.lng,
                "accuracy_m": p.accuracy_m,
                "battery_pct": p.battery_pct,
                "recorded_at": p.recorded_at,
                "route_distance_km": round(placed.distance_km, 4),
                "off_route_m": round(placed.off_route_m, 1),
                "off_route": off,
            }
        )
        seen = latest.get(assigned.tracker_id)
        if seen is None or p.recorded_at > seen[0]:
            latest[assigned.tracker_id] = (p.recorded_at, p.battery_pct)

    if rows:
        await session.execute(insert(GpsPosition), rows)
        await session.execute(
            update(Tracker),
            [
                {"id": tid, "last_seen_at": at, "battery_pct": battery}
                for tid, (at, battery) in latest.items()
            ],
        )
    await session.commit()
    return stats


def decode_entries(entries: list[tuple[str, dict[str, str]]]) -> list[GpsPositionIn]:
    """Stream entries back into positions (skipping anything malformed)."""
    out = []
    for entry_id, fields in entries:
        try:
            out.append(GpsPositionIn.model_validate(json.loads(fields["p"])))
        except (KeyError, ValueError):
            log.warning("Dropping malformed GPS stream entry %s", entry_id)
    return out


async def delete_old_positions(session: AsyncSession, days: int = 30, chunk: int = 50_000) -> int:
    """Delete location history older than `days` (privacy promise to runners). Commits."""
    cutoff = datetime.now(UTC).timestamp() - days * 86_400
    cutoff_at = datetime.fromtimestamp(cutoff, UTC)
    total = 0
    while True:
        ids = select(GpsPosition.id).where(GpsPosition.recorded_at < cutoff_at).limit(chunk)
        result = await session.execute(
            delete(GpsPosition).where(GpsPosition.id.in_(ids.scalar_subquery()))
        )
        await session.commit()
        deleted = result.rowcount or 0  # type: ignore[attr-defined]
        total += deleted
        if deleted < chunk:
            return total
