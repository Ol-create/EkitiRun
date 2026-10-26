"""GPS ingestion: queue, writer, retention (E13)."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.security import create_verification_token
from app.models import Category, Checkpoint, GpsPosition, Tracker
from app.modules.gps import ingest
from app.modules.gps.schemas import GpsPositionIn
from app.modules.registrations import service as registrations
from app.modules.registrations.schemas import RegistrationIn
from app.workers import gps_writer
from scripts.seed import seed

NOW = datetime.now(UTC).replace(microsecond=0)
SECRET = {"X-Gateway-Secret": settings.gateway_secret}


@pytest.fixture
async def course(session):
    """A half marathoner wearing TRK-0001, a spare TRK-0002, and the 10 km checkpoint."""
    await seed(session)
    half = await session.scalar(select(Category).where(Category.code == "HALF"))
    out = await registrations.register(
        session,
        RegistrationIn(
            verification_token=create_verification_token("+2348031234567"),
            first_name="Ada",
            last_name="Okafor",
            gender="F",
            date_of_birth=date(1990, 1, 1),
            category_id=half.id,
            emergency_contact_name="Chidi Okafor",
            emergency_contact_phone="+2348099998888",
            tracking_consent=True,
        ),
    )
    worn = Tracker(device_id="864000000000001", label="TRK-0001", status="assigned",
                   runner_id=out.runner_id, assigned_at=NOW)  # fmt: skip
    spare = Tracker(device_id="864000000000002", label="TRK-0002")
    session.add_all([worn, spare])
    cp10 = await session.scalar(
        select(Checkpoint).where(Checkpoint.route_id == half.route_id, Checkpoint.code == "CP10")
    )
    await session.flush()
    return worn, spare, cp10


def point(device="864000000000001", lat=7.6, lng=5.2, at=NOW, battery=80) -> GpsPositionIn:
    return GpsPositionIn(device_id=device, lat=lat, lng=lng, recorded_at=at, battery_pct=battery)


# ---------------------------------------------------------------- API


async def test_positions_are_queued(client, redis):
    body = {"positions": [point().model_dump(mode="json"), point(lat=7.61).model_dump(mode="json")]}

    response = await client.post("/api/v1/gps/positions", json=body, headers=SECRET)

    assert (response.status_code, response.json()) == (202, {"accepted": 2})
    assert await redis.xlen(ingest.STREAM) == 2


@pytest.mark.parametrize(
    ("headers", "query", "status"),
    [
        ({}, "", 401),
        ({"X-Gateway-Secret": "wrong"}, "", 401),
        ({}, f"?secret={settings.gateway_secret}", 202),
    ],
)
async def test_gateway_secret(client, redis, headers, query, status):
    body = {"positions": [point().model_dump(mode="json")]}

    response = await client.post(f"/api/v1/gps/positions{query}", json=body, headers=headers)

    assert response.status_code == status


async def test_traccar_forwarding_format(client, redis):
    payload = {
        "position": {
            "latitude": 7.6262,
            "longitude": 5.2281,
            "accuracy": 4.5,
            "fixTime": "2027-03-06T07:31:05.000+00:00",
            "attributes": {"batteryLevel": 83.0, "motion": True},
        },
        "device": {"uniqueId": "864000000000001", "name": "TRK-0001"},
    }

    ok = await client.post("/api/v1/gps/traccar", json=payload, headers=SECRET)
    junk = await client.post("/api/v1/gps/traccar", json={"device": {}}, headers=SECRET)

    assert ok.json() == {"accepted": 1}
    assert junk.json() == {"accepted": 0}
    [(_, fields)] = await redis.xrange(ingest.STREAM)
    queued = GpsPositionIn.model_validate_json(fields["p"])
    assert (queued.device_id, queued.lat, queued.battery_pct, queued.accuracy_m) == (
        "864000000000001", 7.6262, 83, 4.5,
    )  # fmt: skip


# ---------------------------------------------------------------- writer


async def test_writer_saves_assigned_trackers_only(session, course):
    worn, spare, cp10 = course
    batch = [
        point(lat=cp10.lat, lng=cp10.lng, at=NOW, battery=81),
        point(lat=cp10.lat, lng=cp10.lng + 0.0027, at=NOW + timedelta(seconds=5), battery=80),
        point(device=spare.device_id, lat=cp10.lat, lng=cp10.lng),
        point(device="999999999999999"),
    ]

    stats = await ingest.write_batch(session, ingest.TrackerIndex(), batch)

    assert (stats.saved, stats.off_route, stats.ignored) == (2, 1, 2)
    on, off = await session.scalars(select(GpsPosition).order_by(GpsPosition.recorded_at))
    assert on.runner_id == worn.runner_id and on.tracker_id == worn.id
    assert on.route_distance_km == pytest.approx(10.0, abs=0.01)
    assert (on.off_route, off.off_route) == (False, True)
    assert off.off_route_m == pytest.approx(285, abs=10)
    await session.refresh(worn)
    assert (worn.last_seen_at, worn.battery_pct) == (NOW + timedelta(seconds=5), 80)


async def test_stream_entries_are_acknowledged_only_after_saving(
    session, course, redis, monkeypatch
):
    class TestSession:  # the writer opens its own sessions; give it the test one
        async def __aenter__(self):
            return session

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(gps_writer, "SessionLocal", TestSession)
    await gps_writer.ensure_group(redis)
    await ingest.queue_positions(redis, [point(), point(at=NOW + timedelta(seconds=5))])
    trackers = ingest.TrackerIndex()

    async def broken(*args):
        raise ConnectionError("database down")

    monkeypatch.setattr(gps_writer, "write_batch", broken)
    with pytest.raises(ConnectionError):
        await gps_writer.process_once(redis, trackers, "writer-1")
    assert (await redis.xpending(ingest.STREAM, ingest.GROUP))["pending"] == 2  # kept

    monkeypatch.setattr(gps_writer, "write_batch", ingest.write_batch)
    monkeypatch.setattr(gps_writer, "RECLAIM_IDLE_MS", 0)  # reclaim straight away
    assert await gps_writer.process_once(redis, trackers, "writer-2") == 2
    assert (await redis.xpending(ingest.STREAM, ingest.GROUP))["pending"] == 0
    assert await session.scalar(select(func.count()).select_from(GpsPosition)) == 2


async def test_old_history_is_deleted(session, course):
    worn, _, _ = course
    for days in (45, 31, 29, 1):
        session.add(GpsPosition(tracker_id=worn.id, runner_id=worn.runner_id, lat=7.6, lng=5.2,
                                recorded_at=NOW - timedelta(days=days)))  # fmt: skip
    await session.flush()

    deleted = await ingest.delete_old_positions(session, days=30, chunk=1)

    assert deleted == 2
    left = await session.scalars(select(GpsPosition.recorded_at).order_by(GpsPosition.recorded_at))
    assert [NOW - at for at in left] == [timedelta(days=29), timedelta(days=1)]


async def test_an_assigned_tracker_needs_a_runner(session):
    session.add(Tracker(device_id="1", label="TRK-9999", status="assigned"))

    with pytest.raises(IntegrityError):
        await session.flush()
