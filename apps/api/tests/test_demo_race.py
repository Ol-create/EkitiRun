"""The demo race script (scripts/demo_race.py) builds a believable race and plays it
through the real API."""

import random
from collections import Counter
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select

from app.core.security import create_verification_token
from app.models import Category, Runner, Scan, Tracker
from app.modules.gps import ingest
from app.modules.gps.live import LIVE_KEY
from app.modules.registrations import service as registrations
from app.modules.registrations.schemas import RegistrationIn
from app.modules.timing import service as timing
from app.workers import gps_writer
from scripts import demo_race
from scripts.seed import seed


def test_runner_behaviour_comes_from_the_bib():
    codes = ["START", "CP5", "CP10", "FINISH"]
    a = demo_race.Plan.for_bib("H0042", "HALF", 21.0975, codes)
    b = demo_race.Plan.for_bib("H0042", "HALF", 21.0975, codes)

    assert a == b
    assert 210 <= a.pace_s_per_km <= 450
    assert a.distance_at(0, 21.0975) == 0
    assert a.distance_at(10**6, 21.0975) == (a.dnf_at_km or 21.0975)


async def test_setup_builds_a_believable_race(session, redis):
    await seed(session)

    summary = await demo_race.setup(session, runners=200, started_minutes_ago=75)

    assert summary["runners"] == 200
    assert 170 <= summary["trackers"] <= 200  # about 5% have no tracker
    per_race = Counter(
        code
        for (code,) in await session.execute(
            select(Category.code).join(Runner, Runner.category_id == Category.id)
        )
    )
    assert per_race == {"FULL": 40, "HALF": 70, "10K": 50, "FUN": 40}
    statuses = Counter()
    for category in await session.scalars(select(Category)):
        assert category.gun_start_at is not None
        for s in await timing.compute_standings(session, category):
            statuses[(category.code, s.status)] += 1
    assert statuses[("FUN", "finished")] > 20  # 5 km in 75 minutes
    assert statuses[("FULL", "started")] > 20  # nobody runs a marathon in 75 minutes
    assert statuses[("FULL", "finished")] == 0


async def test_reset_removes_only_demo_data(session):
    await seed(session)
    half = await session.scalar(select(Category).where(Category.code == "HALF"))
    real = await registrations.register(
        session,
        RegistrationIn(
            verification_token=create_verification_token("+2348031234567"),
            first_name="Real",
            last_name="Runner",
            gender="F",
            date_of_birth=date(1990, 1, 1),
            category_id=half.id,
            emergency_contact_name="Kin Name",
            emergency_contact_phone="+2348099998888",
            tracking_consent=True,
        ),
    )
    await demo_race.setup(session, runners=40, started_minutes_ago=30)

    removed = await demo_race.reset(session)

    assert removed["runners"] == 40
    assert [r.id for r in await session.scalars(select(Runner))] == [real.runner_id]
    assert await session.scalar(select(func.count()).select_from(Tracker)) == 0


async def test_live_play_goes_through_the_real_pipeline(db_client, session, redis, monkeypatch):
    await seed(session)
    await demo_race.setup(session, runners=60, started_minutes_ago=40)
    runners, courses = await demo_race.load(session)
    assert sum(len(r.scanned) for r in runners) > 0  # past scans are known

    class TestSession:  # the GPS writer opens its own sessions; give it the test one
        async def __aenter__(self):
            return session

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(gps_writer, "SessionLocal", TestSession)
    await gps_writer.ensure_group(redis)
    scans_before = await session.scalar(select(func.count()).select_from(Scan))

    report = await demo_race.tick(
        db_client, runners, courses, datetime.now(UTC) + timedelta(minutes=12), random.Random(1)
    )
    while await gps_writer.process_once(redis, ingest.TrackerIndex(), "writer-1"):
        pass

    assert report.gps_sent > 30
    assert report.scans_accepted > 0
    assert await session.scalar(select(func.count()).select_from(Scan)) > scans_before
    assert await redis.hlen(LIVE_KEY) > 30  # dots on the live map
