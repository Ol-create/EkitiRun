"""Live runner positions for the maps. Owner: Lead (E14).

The GPS writer calls `update_live()` after saving each batch. For every runner it
keeps ONE live position in the Redis hash "live:positions" and announces it on the
channel "positions:{bib}" (GET /stream/positions).

Smoothing, so the dot on the map behaves:
- The point is placed on the course, searching only near where the runner was
  last seen. On a loop (start = finish) or a road used twice, the nearest bit of
  course can be the wrong pass; near the last position it never is.
- The dot is drawn ON the course line at that distance, so GPS noise doesn't make
  it zigzag across the road.
- Distance never goes back more than 100 m, and forward jumps faster than
  8 m/s are held, so a bad fix doesn't throw the runner around.
- Older (out-of-order) fixes and points over 200 m off the course are ignored.

GET /positions reads a snapshot of every runner on course that is rebuilt at most
every 5 s, by one request at a time, so spectators never wait on Postgres.
"""

import json
import logging
from collections.abc import Awaitable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, cast

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.broadcast import publish
from app.core.schemas import LivePosition
from app.models import Category
from app.modules.gps.ingest import OFF_ROUTE_M, AssignedTracker, TrackerIndex
from app.modules.gps.schemas import GpsPositionIn, PositionEvent, PositionsSnapshot, RunnerPosition
from app.modules.timing import service as timing

log = logging.getLogger("ekitirun.gps")

LIVE_KEY = "live:positions"
STALE_AFTER_S = 120
MAX_BACKWARD_KM = 0.1
MAX_SPEED_KM_PER_S = 0.008  # 8 m/s: faster than any marathoner
JUMP_SLACK_KM = 0.2  # GPS error allowance on top of running speed
SEARCH_BEHIND_KM = 0.3
FIRST_FIX_TIE_M = 30.0  # first fix: prefer the earlier pass if it fits nearly as well
SNAPSHOT_FRESH_S = 5
SNAPSHOT_KEEP_S = 120


def channel(bib: str) -> str:
    return f"positions:{bib}"


@dataclass
class LiveState:
    runner_id: str
    bib_number: str
    category_code: str
    gender: str
    lat: float
    lng: float
    distance_km: float
    recorded_at: str  # ISO
    battery_pct: int | None = None

    def is_stale(self, now: datetime) -> bool:
        age = (now - datetime.fromisoformat(self.recorded_at)).total_seconds()
        return age > STALE_AFTER_S

    def live_position(self, now: datetime) -> LivePosition:
        return LivePosition(
            lat=self.lat,
            lng=self.lng,
            distance_km=self.distance_km,
            recorded_at=datetime.fromisoformat(self.recorded_at),
            is_stale=self.is_stale(now),
        )


def _place(assigned: AssignedTracker, p: GpsPositionIn, prev: LiveState | None):
    """(distance_km, off_route_m) for this fix, searching near the previous position."""
    course = assigned.course
    if prev is None:
        placed = course.place(p.lat, p.lng)
        if placed.distance_km > 0.5:  # does an earlier pass of the course fit nearly as well?
            earlier = course.place_between(p.lat, p.lng, 0, placed.distance_km - 0.5)
            if earlier.off_route_m <= placed.off_route_m + FIRST_FIX_TIE_M:
                placed = earlier
        return placed.distance_km, placed.off_route_m
    elapsed_s = max(0.0, (p.recorded_at - datetime.fromisoformat(prev.recorded_at)).total_seconds())
    reach = prev.distance_km + MAX_SPEED_KM_PER_S * elapsed_s + JUMP_SLACK_KM
    placed = course.place_between(p.lat, p.lng, prev.distance_km - SEARCH_BEHIND_KM, reach)
    return placed.distance_km, placed.off_route_m


def next_state(
    assigned: AssignedTracker, p: GpsPositionIn, prev: LiveState | None
) -> LiveState | None:
    """The runner's new live state after fix `p`, or None to keep the previous one."""
    if prev is not None and p.recorded_at <= datetime.fromisoformat(prev.recorded_at):
        return None  # an older fix arriving late
    distance_km, off_route_m = _place(assigned, p, prev)
    if off_route_m > OFF_ROUTE_M:
        return None
    if prev is not None and distance_km < prev.distance_km - MAX_BACKWARD_KM:
        distance_km = prev.distance_km  # jitter or a wrong pass: hold the runner where they were
    lat, lng = assigned.course.point_at(distance_km)
    return LiveState(
        runner_id=str(assigned.runner_id),
        bib_number=assigned.bib_number,
        category_code=assigned.category_code,
        gender=assigned.gender,
        lat=round(lat, 6),
        lng=round(lng, 6),
        distance_km=round(distance_km, 3),
        recorded_at=p.recorded_at.isoformat(),
        battery_pct=p.battery_pct,
    )


async def _load(redis: Redis, runner_ids: list[str]) -> dict[str, LiveState]:
    if not runner_ids:
        return {}
    values = await cast(Awaitable[list[str | None]], redis.hmget(LIVE_KEY, runner_ids))
    return {rid: LiveState(**json.loads(v)) for rid, v in zip(runner_ids, values, strict=True) if v}


async def update_live(redis: Redis, trackers: TrackerIndex, positions: list[GpsPositionIn]) -> int:
    """Move runners' live positions after a saved batch and announce them. Returns how many."""
    fixes: dict[str, tuple[AssignedTracker, list[GpsPositionIn]]] = {}
    for p in sorted(positions, key=lambda p: p.recorded_at):
        assigned = trackers.by_device.get(p.device_id)
        if assigned is not None:
            fixes.setdefault(str(assigned.runner_id), (assigned, []))[1].append(p)

    previous = await _load(redis, list(fixes))
    updated: dict[str, LiveState] = {}
    for rid, (assigned, runner_fixes) in fixes.items():
        state = previous.get(rid)
        for p in runner_fixes:  # in time order, so smoothing sees every fix
            state = next_state(assigned, p, state) or state
        if state is not None and state is not previous.get(rid):
            updated[rid] = state
    if not updated:
        return 0

    mapping = {rid: json.dumps(asdict(s)) for rid, s in updated.items()}
    await cast(Awaitable[int], redis.hset(LIVE_KEY, mapping=mapping))
    now = datetime.now(UTC)
    for state in updated.values():
        event = PositionEvent(bib_number=state.bib_number, **state.live_position(now).model_dump())
        try:
            await publish(redis, channel(state.bib_number), event.model_dump(mode="json"))
        except Exception as exc:  # live updates are a bonus: never fail the writer
            log.warning("Couldn't publish position of %s: %s", state.bib_number, exc)
    return len(updated)


async def get_live_position(redis: Redis, runner_id: Any) -> LivePosition | None:
    """For B3's runner page: the latest live position, or None (no tracker or no fix yet)."""
    raw = await cast(Awaitable[str | None], redis.hget(LIVE_KEY, str(runner_id)))
    return LiveState(**json.loads(raw)).live_position(datetime.now(UTC)) if raw else None


async def _finished_or_out(session: AsyncSession, redis: Redis, codes: set[str]) -> set[str]:
    """Bibs of runners who finished or are DNF: they leave the live map."""
    gone: set[str] = set()
    for category in await session.scalars(select(Category).where(Category.code.in_(codes))):
        for s in await timing.standings(session, redis, category):
            if s.status in ("finished", "dnf"):
                gone.add(s.bib_number)
    return gone


async def build_snapshot(session: AsyncSession, redis: Redis) -> PositionsSnapshot:
    now = datetime.now(UTC)
    raw = await cast(Awaitable[dict[str, str]], redis.hgetall(LIVE_KEY))
    states = [LiveState(**json.loads(v)) for v in raw.values()]
    gone = await _finished_or_out(session, redis, {s.category_code for s in states})
    runners = [
        RunnerPosition(
            bib_number=s.bib_number,
            category_code=s.category_code,
            gender=s.gender,  # type: ignore[arg-type]
            lat=s.lat,
            lng=s.lng,
            distance_km=s.distance_km,
            is_stale=s.is_stale(now),
        )
        for s in states
        if s.bib_number not in gone
    ]
    runners.sort(key=lambda r: (r.category_code, r.bib_number))
    return PositionsSnapshot(updated_at=now, runners=runners)


async def snapshot(session: AsyncSession, redis: Redis, category: str | None) -> PositionsSnapshot:
    """Every runner on course, from a cached snapshot rebuilt at most every 5 s."""
    data_key, fresh_key, lock_key = (
        "positions:snapshot",
        "positions:snapshot:fresh",
        "positions:snapshot:lock",
    )
    cached, fresh = await redis.mget(data_key, fresh_key)
    locked = False
    if cached is None or not fresh:
        locked = bool(await redis.set(lock_key, "1", nx=True, ex=10))
    if locked or cached is None:
        try:
            built = await build_snapshot(session, redis)
            cached = built.model_dump_json()
            await redis.set(data_key, cached, ex=SNAPSHOT_KEEP_S)
            await redis.set(fresh_key, "1", ex=SNAPSHOT_FRESH_S)
        finally:
            if locked:
                await redis.delete(lock_key)
    result = PositionsSnapshot.model_validate_json(cached)
    if category:
        code = category.upper()
        result.runners = [r for r in result.runners if r.category_code == code]
    return result
