"""Live positions: smoothing, snapshot, stream (E14)."""

import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.broadcast import broadcaster
from app.core.security import create_verification_token
from app.models import Category, Checkpoint, Scan, Tracker
from app.modules.gps import ingest, live
from app.modules.gps import service as gps_service
from app.modules.gps.schemas import GpsPositionIn
from app.modules.registrations import service as registrations
from app.modules.registrations.schemas import RegistrationIn
from scripts.seed import seed

T0 = datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=30)


class Race:
    """Runners wearing trackers, and helpers to send fixes at a course distance."""

    def __init__(self, session, redis):
        self.session, self.redis = session, redis
        self.index = ingest.TrackerIndex()
        self.devices: dict[str, str] = {}  # bib -> device id

    async def runner(self, code: str, n: int) -> str:
        category = await self.session.scalar(select(Category).where(Category.code == code))
        out = await registrations.register(
            self.session,
            RegistrationIn(
                verification_token=create_verification_token(f"+23480312345{n:02d}"),
                first_name="Runner",
                last_name=str(n),
                gender="F",
                date_of_birth=date(1990, 1, 1),
                category_id=category.id,
                emergency_contact_name="Kin Name",
                emergency_contact_phone="+2348099998888",
                tracking_consent=True,
            ),
        )
        device = f"86400000000{n:04d}"
        self.session.add(Tracker(device_id=device, label=f"TRK-{n:04d}", status="assigned",
                                 runner_id=out.runner_id))  # fmt: skip
        await self.session.flush()
        await self.index.refresh(self.session, force=True)
        self.devices[out.bib_number] = device
        return out.bib_number

    def course(self, bib: str):
        return self.index.by_device[self.devices[bib]].course

    def fix(self, bib: str, km: float, seconds: float, east_m: float = 0.0) -> GpsPositionIn:
        lat, lng = self.course(bib).point_at(km)
        lng += east_m / self.course(bib).m_per_deg_lng
        return GpsPositionIn(
            device_id=self.devices[bib], lat=lat, lng=lng,
            recorded_at=T0 + timedelta(seconds=seconds), battery_pct=77,
        )  # fmt: skip

    async def send(self, *fixes: GpsPositionIn) -> int:
        return await live.update_live(self.redis, self.index, list(fixes))

    async def km(self, bib: str) -> float | None:
        runner_id = self.index.by_device[self.devices[bib]].runner_id
        position = await live.get_live_position(self.redis, runner_id)
        return None if position is None else position.distance_km


@pytest.fixture
async def race(session, redis) -> Race:
    await seed(session)
    return Race(session, redis)


# ---------------------------------------------------------------- smoothing


async def test_runner_moves_along_the_course(race):
    bib = await race.runner("HALF", 1)

    await race.send(race.fix(bib, 2.0, 0, east_m=12))  # 12 m GPS noise beside the road
    await race.send(race.fix(bib, 2.3, 60))

    assert await race.km(bib) == pytest.approx(2.3, abs=0.005)
    position = await live.get_live_position(
        race.redis, race.index.by_device[race.devices[bib]].runner_id
    )
    on_course = race.course(bib).point_at(2.3)
    assert (position.lat, position.lng) == pytest.approx(on_course, abs=1e-5)  # drawn on the line


async def test_small_jitter_back_is_allowed_but_big_jumps_back_are_held(race):
    bib = await race.runner("HALF", 1)
    await race.send(race.fix(bib, 5.0, 0))

    await race.send(race.fix(bib, 4.95, 10))
    assert await race.km(bib) == pytest.approx(4.95, abs=0.005)

    await race.send(race.fix(bib, 4.75, 20))  # 200 m back
    assert await race.km(bib) == pytest.approx(4.95, abs=0.005)


async def test_impossible_forward_jumps_are_ignored(race):
    bib = await race.runner("HALF", 1)
    await race.send(race.fix(bib, 2.0, 0))

    await race.send(race.fix(bib, 6.0, 10))  # 4 km in 10 s

    assert await race.km(bib) == pytest.approx(2.0, abs=0.005)


async def test_late_and_off_route_fixes_are_ignored(race):
    bib = await race.runner("HALF", 1)
    await race.send(race.fix(bib, 3.0, 100))

    late = await race.send(race.fix(bib, 2.0, 50))
    off = await race.send(race.fix(bib, 3.1, 120, east_m=400))

    assert (late, off) == (0, 0)
    assert await race.km(bib) == pytest.approx(3.0, abs=0.005)


async def test_loop_course_start_and_finish_are_told_apart(race):
    """The full marathon starts and finishes at the same spot."""
    bib = await race.runner("FULL", 1)
    total = race.course(bib).length_km

    await race.send(race.fix(bib, 0.0, 0))
    assert await race.km(bib) == pytest.approx(0.0, abs=0.01)

    await race.send(race.fix(bib, total - 0.1, 9_000), race.fix(bib, total, 9_030))
    assert await race.km(bib) == pytest.approx(total, abs=0.01)


async def test_fixes_are_announced_on_the_runners_channel(race):
    bib = await race.runner("HALF", 1)
    async with broadcaster(race.redis, "positions:*").listen(live.channel(bib)) as messages:
        await race.send(race.fix(bib, 1.0, 0))
        event = await asyncio.wait_for(anext(messages), 2)

    assert event["bib_number"] == bib
    assert event["distance_km"] == pytest.approx(1.0, abs=0.005)


# ---------------------------------------------------------------- snapshot


async def test_snapshot_lists_runners_on_course(race, session):
    half_a = await race.runner("HALF", 1)
    half_b = await race.runner("HALF", 2)
    full = await race.runner("FULL", 3)
    now_s = (datetime.now(UTC) - T0).total_seconds()
    await race.send(race.fix(half_a, 5.0, now_s - 10))
    await race.send(race.fix(half_b, 4.0, now_s - 600))  # last fix 10 minutes ago
    await race.send(race.fix(full, 9.0, now_s - 5))

    snap = await live.snapshot(session, race.redis, None)
    halves = await live.snapshot(session, race.redis, "half")

    assert {(r.bib_number, r.is_stale) for r in snap.runners} == {
        (half_a, False), (half_b, True), (full, False),
    }  # fmt: skip
    assert {r.bib_number for r in halves.runners} == {half_a, half_b}


async def test_finishers_leave_the_live_map(race, session):
    bib = await race.runner("HALF", 1)
    await race.send(race.fix(bib, 21.0, 0))
    half = await session.scalar(select(Category).where(Category.code == "HALF"))
    finish = await session.scalar(
        select(Checkpoint).where(Checkpoint.route_id == half.route_id, Checkpoint.is_finish)
    )
    runner_id = race.index.by_device[race.devices[bib]].runner_id
    session.add(Scan(client_id=uuid.uuid4(), runner_id=runner_id, checkpoint_id=finish.id,
                     device_id="p", scanned_at=T0))  # fmt: skip
    await session.flush()

    snap = await live.snapshot(session, race.redis, None)

    assert snap.runners == []


async def test_snapshot_is_cached_for_five_seconds(race, session):
    bib = await race.runner("HALF", 1)
    await race.send(race.fix(bib, 1.0, 0))
    first = await live.snapshot(session, race.redis, None)

    await race.send(race.fix(bib, 1.2, 60))
    cached = await live.snapshot(session, race.redis, None)
    await race.redis.delete("positions:snapshot:fresh")  # 5 s later
    fresh = await live.snapshot(session, race.redis, None)

    assert cached.runners == first.runners
    assert fresh.runners[0].distance_km == pytest.approx(1.2, abs=0.005)


# ---------------------------------------------------------------- stream and endpoints


async def test_stream_starts_with_the_current_position(race, session):
    bib = await race.runner("HALF", 1)
    await race.send(race.fix(bib, 1.0, 0))
    stream = gps_service.position_events(session, race.redis, bib)

    first = await asyncio.wait_for(anext(stream), 2)
    following = asyncio.create_task(anext(stream))
    await asyncio.sleep(0.05)
    await race.send(race.fix(bib, 1.3, 90))
    second = await asyncio.wait_for(following, 2)

    assert first.distance_km == pytest.approx(1.0, abs=0.005)
    assert first.is_stale is True  # its fix is about 30 minutes old
    assert second.distance_km == pytest.approx(1.3, abs=0.005)
    await stream.aclose()


async def test_endpoints(db_client, race):
    bib = await race.runner("HALF", 1)
    await race.send(race.fix(bib, 1.0, 0))

    snap = await db_client.get("/api/v1/positions", params={"category": "HALF"})
    missing = await db_client.get("/api/v1/stream/positions", params={"bib": "X9999"})

    assert [r["bib_number"] for r in snap.json()["runners"]] == [bib]
    assert (missing.status_code, missing.json()["code"]) == (404, "RUNNER_NOT_FOUND")


async def test_gps_writer_updates_live_positions(race, session, monkeypatch):
    from app.workers import gps_writer

    class TestSession:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(gps_writer, "SessionLocal", TestSession)
    bib = await race.runner("HALF", 1)
    await gps_writer.ensure_group(race.redis)
    await ingest.queue_positions(race.redis, [race.fix(bib, 2.5, 0)])

    await gps_writer.process_once(race.redis, race.index, "writer-1")

    assert await race.km(bib) == pytest.approx(2.5, abs=0.005)
