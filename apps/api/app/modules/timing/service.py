"""Timing engine: splits, finish times and rankings from checkpoint scans. Owner: Lead (E9).

Times
- A scan's time is the phone's time corrected for its clock drift
  (`scanned_at + clock_offset_ms`, measured in E8).
- Elapsed time is measured from the category's gun start (`gun_start_at`). Until
  the gun is recorded, elapsed times are unknown and runners rank by distance.
- The finish time is the elapsed time at the finish checkpoint.

Ranking (per category)
1. Finishers, fastest first.
2. Runners on course, furthest checkpoint first; at the same checkpoint, whoever
   reached it first.
3. DNF runners (marked by the race office), furthest first.
Registered runners with no scans aren't ranked.
`position` is the place in the race (all genders); `position_gender` the place
among runners of the same gender.

Caching
Standings live in Redis, so spectators never hit Postgres. Each scan batch marks
its categories as changed; the next read rebuilds them. Only one request rebuilds
at a time (a short Redis lock): the others are served the previous standings.

For Backend (B3): use `get_runner_result()` for a runner's splits and positions.
"""

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category, Checkpoint, Runner, Scan

CACHE_TTL_S = 3600  # safety net: standings are rebuilt on change anyway
LOCK_TTL_S = 10


@dataclass
class Split:
    checkpoint_id: int
    checkpoint_name: str
    distance_km: float
    scanned_at: datetime  # clock-corrected
    elapsed_seconds: int | None  # None until the gun start is recorded


@dataclass
class Standing:
    runner_id: str
    bib_number: str
    full_name: str
    gender: str
    category_code: str
    status: str  # started | finished | dnf
    last_checkpoint: str | None
    last_distance_km: float
    elapsed_seconds: int | None  # at the last checkpoint
    finish_seconds: int | None
    position: int = 0
    position_gender: int = 0


@dataclass
class RunnerResult:
    status: str  # registered | started | finished | dnf
    splits: list[Split] = field(default_factory=list)
    finish_seconds: int | None = None
    position_overall: int | None = None  # set once finished
    position_category: int | None = None  # place within gender, once finished


def corrected_time(scan: Scan) -> datetime:
    return scan.scanned_at + timedelta(milliseconds=scan.clock_offset_ms or 0)


def elapsed(at: datetime, gun: datetime | None) -> int | None:
    return None if gun is None else max(0, round((at - gun).total_seconds()))


def _splits(scans: list[tuple[Scan, Checkpoint]], gun: datetime | None) -> list[Split]:
    rows = [
        Split(
            checkpoint_id=cp.id,
            checkpoint_name=cp.name,
            distance_km=float(cp.distance_km),
            scanned_at=corrected_time(scan),
            elapsed_seconds=elapsed(corrected_time(scan), gun),
        )
        for scan, cp in scans
    ]
    return sorted(rows, key=lambda s: (s.distance_km, s.scanned_at))


def _status(runner: Runner, splits: list[Split], finish_id: int | None) -> str:
    if runner.status == "dnf":
        return "dnf"
    if finish_id is not None and any(s.checkpoint_id == finish_id for s in splits):
        return "finished"
    return "started" if splits else "registered"


def _rank_key(s: Standing) -> tuple:
    if s.status == "finished":
        return (0, s.finish_seconds if s.finish_seconds is not None else 0, 0.0, s.bib_number)
    group = 1 if s.status == "started" else 2
    at = s.elapsed_seconds if s.elapsed_seconds is not None else 0
    return (group, -s.last_distance_km, at, s.bib_number)


async def _category_scans(
    session: AsyncSession, category: Category
) -> tuple[list[Runner], dict[uuid.UUID, list[tuple[Scan, Checkpoint]]], int | None]:
    runners = list(await session.scalars(select(Runner).where(Runner.category_id == category.id)))
    rows = await session.execute(
        select(Scan, Checkpoint)
        .join(Checkpoint, Checkpoint.id == Scan.checkpoint_id)
        .join(Runner, Runner.id == Scan.runner_id)
        .where(Runner.category_id == category.id, Checkpoint.route_id == category.route_id)
    )
    by_runner: dict[uuid.UUID, list[tuple[Scan, Checkpoint]]] = {}
    for scan, cp in rows:
        by_runner.setdefault(scan.runner_id, []).append((scan, cp))
    finish_id = await session.scalar(
        select(Checkpoint.id).where(
            Checkpoint.route_id == category.route_id, Checkpoint.is_finish.is_(True)
        )
    )
    return runners, by_runner, finish_id


async def compute_standings(session: AsyncSession, category: Category) -> list[Standing]:
    """Rank every runner in the category who has started. Reads Postgres."""
    runners, by_runner, finish_id = await _category_scans(session, category)
    gun = category.gun_start_at
    standings = []
    for runner in runners:
        splits = _splits(by_runner.get(runner.id, []), gun)
        status = _status(runner, splits, finish_id)
        if status == "registered":
            continue
        last = splits[-1] if splits else None
        standings.append(
            Standing(
                runner_id=str(runner.id),
                bib_number=runner.bib_number,
                full_name=f"{runner.first_name} {runner.last_name}",
                gender=runner.gender,
                category_code=category.code,
                status=status,
                last_checkpoint=last.checkpoint_name if last else None,
                last_distance_km=last.distance_km if last else 0.0,
                elapsed_seconds=last.elapsed_seconds if last else None,
                finish_seconds=last.elapsed_seconds if status == "finished" and last else None,
            )
        )
    standings.sort(key=_rank_key)
    per_gender: dict[str, int] = {}
    for position, s in enumerate(standings, start=1):
        s.position = position
        per_gender[s.gender] = per_gender.get(s.gender, 0) + 1
        s.position_gender = per_gender[s.gender]
    return standings


# ---------------------------------------------------------------- cache


def _keys(category_id: int) -> tuple[str, str, str]:
    base = f"standings:{category_id}"
    return base, f"{base}:dirty", f"{base}:lock"


async def mark_changed(redis: Redis, category_ids: set[int]) -> None:
    """Call after scans or race-office changes: the next read rebuilds these standings."""
    if category_ids:
        await redis.mset({_keys(cid)[1]: "1" for cid in category_ids})


async def standings(session: AsyncSession, redis: Redis, category: Category) -> list[Standing]:
    """The category's standings, from Redis when up to date."""
    data_key, dirty_key, lock_key = _keys(category.id)
    cached, dirty = await redis.mget(data_key, dirty_key)
    if cached is not None and not dirty:
        return [Standing(**s) for s in json.loads(cached)]

    locked = bool(await redis.set(lock_key, "1", nx=True, ex=LOCK_TTL_S))
    if cached is not None and not locked:
        return [Standing(**s) for s in json.loads(cached)]  # someone else is rebuilding
    # (With nothing cached at all, rebuild even without the lock: there is nothing to serve.)

    try:
        await redis.delete(dirty_key)  # changes arriving during the rebuild mark it again
        fresh = await compute_standings(session, category)
        await redis.set(data_key, json.dumps([asdict(s) for s in fresh]), ex=CACHE_TTL_S)
        return fresh
    finally:
        if locked:
            await redis.delete(lock_key)


async def get_runner_result(
    session: AsyncSession, redis: Redis, runner_id: uuid.UUID
) -> RunnerResult | None:
    """A runner's splits, finish time and places. None if the runner doesn't exist."""
    runner = await session.get(Runner, runner_id)
    if runner is None:
        return None
    category = await session.get(Category, runner.category_id)
    assert category is not None
    rows = await session.execute(
        select(Scan, Checkpoint)
        .join(Checkpoint, Checkpoint.id == Scan.checkpoint_id)
        .where(Scan.runner_id == runner.id, Checkpoint.route_id == category.route_id)
    )
    splits = _splits([(scan, cp) for scan, cp in rows], category.gun_start_at)
    finish_id = await session.scalar(
        select(Checkpoint.id).where(
            Checkpoint.route_id == category.route_id, Checkpoint.is_finish.is_(True)
        )
    )
    status = _status(runner, splits, finish_id)
    result = RunnerResult(status=status, splits=splits)
    if status == "finished":
        result.finish_seconds = splits[-1].elapsed_seconds
        mine = next(
            (s for s in await standings(session, redis, category) if s.runner_id == str(runner.id)),
            None,
        )
        if mine:
            result.position_overall, result.position_category = mine.position, mine.position_gender
    return result
