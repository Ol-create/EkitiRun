import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Literal

import pytest
from sqlalchemy import select

from app.core.security import create_qr_token, create_scanner_token, create_verification_token
from app.models import Category, Checkpoint, Runner, Scan
from app.modules.registrations import service as registrations
from app.modules.registrations.schemas import RegistrationIn
from app.modules.timing import service as timing
from scripts.seed import seed

GUN = datetime(2027, 3, 6, 6, 30, tzinfo=UTC)
ADMIN = {"Authorization": "Bearer dev-admin"}
RESULTS = "/api/v1/results"


async def register(session, category, n: int, gender: Literal["M", "F"], first: str) -> Runner:
    out = await registrations.register(
        session,
        RegistrationIn(
            verification_token=create_verification_token(f"+23480312345{n:02d}"),
            first_name=first,
            last_name="Test",
            gender=gender,
            date_of_birth=date(1990, 1, 1),
            category_id=category.id,
            emergency_contact_name="Kin Name",
            emergency_contact_phone="+2348099998888",
            tracking_consent=True,
        ),
    )
    return await session.get(Runner, out.runner_id)


class Race:
    def __init__(self, session, half: Category, checkpoints: dict[str, Checkpoint]):
        self.session, self.half, self.cp = session, half, checkpoints

    async def scan(self, runner: Runner, code: str, minutes: float, offset_ms: int | None = None):
        """`runner` scanned at `code`, `minutes` after the gun (by the phone's clock)."""
        self.session.add(
            Scan(
                client_id=uuid.uuid4(),
                runner_id=runner.id,
                checkpoint_id=self.cp[code].id,
                device_id="phone-test",
                scanned_at=GUN + timedelta(minutes=minutes),
                clock_offset_ms=offset_ms,
            )
        )
        await self.session.flush()


@pytest.fixture
async def race(session) -> Race:
    await seed(session)
    half = await session.scalar(select(Category).where(Category.code == "HALF"))
    half.gun_start_at = GUN
    cps = {
        cp.code: cp
        for cp in await session.scalars(
            select(Checkpoint).where(Checkpoint.route_id == half.route_id)
        )
    }
    await session.flush()
    return Race(session, half, cps)


@pytest.fixture
async def field(session, race):
    """Five half marathoners in different states."""
    ada = await register(session, race.half, 1, "F", "Ada")  # finishes 1:30:00
    bola = await register(session, race.half, 2, "M", "Bola")  # finishes 1:25:00 (winner)
    chi = await register(session, race.half, 3, "F", "Chi")  # at 15 km
    dayo = await register(session, race.half, 4, "M", "Dayo")  # at 10 km, then DNF
    await register(session, race.half, 5, "F", "Ezi")  # registered, never scanned
    for runner, cps in [
        (ada, [("START", 1), ("CP5", 25), ("CP10", 45), ("FINISH", 90)]),
        (bola, [("START", 0.5), ("CP10", 40), ("FINISH", 85)]),
        (chi, [("START", 1), ("CP10", 50), ("CP15", 70)]),
        (dayo, [("START", 2), ("CP10", 55)]),
    ]:
        for code, minutes in cps:
            await race.scan(runner, code, minutes)
    dayo.status = "dnf"
    await session.flush()
    return {"ada": ada, "bola": bola, "chi": chi, "dayo": dayo}


async def test_elapsed_is_measured_from_the_gun_with_clock_correction(session, redis, race):
    ada = await register(session, race.half, 1, "F", "Ada")
    # The phone's clock was 60 s slow: it said 30:00 when it was really 31:00.
    await race.scan(ada, "CP5", 30, offset_ms=60_000)

    result = await timing.get_runner_result(session, redis, ada.id)

    [split] = result.splits
    assert (split.checkpoint_name, split.elapsed_seconds) == ("5 km", 31 * 60)
    assert split.scanned_at == GUN + timedelta(minutes=31)
    assert result.status == "started"
    assert result.finish_seconds is None


async def test_standings_order_and_places(session, race, field):
    standings = await timing.compute_standings(session, race.half)

    assert [(s.bib_number, s.status, s.position, s.position_gender) for s in standings] == [
        (field["bola"].bib_number, "finished", 1, 1),
        (field["ada"].bib_number, "finished", 2, 1),
        (field["chi"].bib_number, "started", 3, 2),
        (field["dayo"].bib_number, "dnf", 4, 2),
    ]
    bola, ada, chi, _ = standings
    assert (bola.finish_seconds, ada.finish_seconds) == (85 * 60, 90 * 60)
    assert (chi.last_checkpoint, chi.elapsed_seconds, chi.finish_seconds) == (
        "15 km",
        70 * 60,
        None,
    )


async def test_same_checkpoint_earlier_arrival_ranks_higher(session, race):
    first = await register(session, race.half, 1, "F", "First")
    second = await register(session, race.half, 2, "F", "Second")
    await race.scan(second, "CP10", 52)
    await race.scan(first, "CP10", 48)

    standings = await timing.compute_standings(session, race.half)

    assert [s.bib_number for s in standings] == [first.bib_number, second.bib_number]


async def test_without_a_gun_time_runners_rank_by_distance(session, race):
    race.half.gun_start_at = None
    behind = await register(session, race.half, 1, "F", "Behind")
    ahead = await register(session, race.half, 2, "F", "Ahead")
    await race.scan(behind, "CP5", 20)
    await race.scan(ahead, "CP10", 45)

    standings = await timing.compute_standings(session, race.half)

    assert [s.bib_number for s in standings] == [ahead.bib_number, behind.bib_number]
    assert all(s.elapsed_seconds is None for s in standings)


async def test_runner_result_for_backend(session, redis, race, field):
    winner = await timing.get_runner_result(session, redis, field["ada"].id)
    running = await timing.get_runner_result(session, redis, field["chi"].id)

    assert [s.checkpoint_name for s in winner.splits] == ["Start", "5 km", "10 km", "Finish"]
    assert (winner.status, winner.finish_seconds) == ("finished", 90 * 60)
    assert (winner.position_overall, winner.position_category) == (2, 1)
    assert (running.position_overall, running.position_category) == (None, None)
    assert await timing.get_runner_result(session, redis, uuid.uuid4()) is None


# ---------------------------------------------------------------- GET /results


async def test_results_leaderboard(db_client, race, field):
    response = await db_client.get(RESULTS, params={"category": "half"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 4
    first = body["items"][0]
    assert first == {
        "position": 1,
        "bib_number": field["bola"].bib_number,
        "full_name": "Bola Test",
        "gender": "M",
        "category_code": "HALF",
        "status": "finished",
        "last_checkpoint": "Finish",
        "elapsed_seconds": 85 * 60,
        "finish_seconds": 85 * 60,
    }


async def test_results_by_gender_use_gender_places(db_client, race, field):
    body = (await db_client.get(RESULTS, params={"category": "HALF", "gender": "F"})).json()

    assert [(i["full_name"], i["position"]) for i in body["items"]] == [
        ("Ada Test", 1),
        ("Chi Test", 2),
    ]


async def test_results_paging(db_client, race, field):
    body = (
        await db_client.get(RESULTS, params={"category": "HALF", "limit": 2, "offset": 2})
    ).json()

    assert body["total"] == 4
    assert [i["position"] for i in body["items"]] == [3, 4]


# ---------------------------------------------------------------- cache


async def test_standings_are_cached_until_something_changes(db_client, session, redis, race, field):
    before = (await db_client.get(RESULTS, params={"category": "HALF"})).json()
    await race.scan(field["chi"], "FINISH", 80)  # not announced yet

    cached = (await db_client.get(RESULTS, params={"category": "HALF"})).json()
    await timing.mark_changed(redis, {race.half.id})
    fresh = (await db_client.get(RESULTS, params={"category": "HALF"})).json()

    assert cached == before
    assert [i["full_name"] for i in fresh["items"][:2]] == ["Chi Test", "Bola Test"]


async def test_scan_upload_refreshes_the_leaderboard(db_client, race, field):
    await db_client.get(RESULTS, params={"category": "HALF"})  # warm the cache
    chi = field["chi"]
    body = {
        "device_id": "phone-finish",
        "checkpoint_id": race.cp["FINISH"].id,
        "scans": [
            {
                "client_id": str(uuid.uuid4()),
                "qr_token": create_qr_token(chi.bib_number, chi.id),
                "scanned_at": (GUN + timedelta(minutes=80)).isoformat(),
            }
        ],
    }
    token = create_scanner_token("phone-finish", race.cp["FINISH"].id)
    upload = await db_client.post(
        "/api/v1/scans/batch", json=body, headers={"Authorization": f"Bearer {token}"}
    )
    assert upload.json()["results"][0]["status"] == "accepted"

    items = (await db_client.get(RESULTS, params={"category": "HALF"})).json()["items"]

    assert (items[0]["full_name"], items[0]["finish_seconds"]) == ("Chi Test", 80 * 60)


async def test_a_rebuild_in_progress_serves_the_previous_standings(session, redis, race, field):
    first = await timing.standings(session, redis, race.half)
    await race.scan(field["chi"], "FINISH", 80)
    await timing.mark_changed(redis, {race.half.id})
    await redis.set(f"standings:{race.half.id}:lock", "1")  # another request is rebuilding

    during = await timing.standings(session, redis, race.half)
    await redis.delete(f"standings:{race.half.id}:lock")
    after = await timing.standings(session, redis, race.half)

    assert during == first
    assert after[0].full_name == "Chi Test"


# ---------------------------------------------------------------- race office


async def test_gun_start(db_client, session, race):
    url = f"/api/v1/admin/categories/{race.half.id}/gun-start"
    at = datetime(2027, 3, 6, 6, 31, 12, tzinfo=UTC)

    assert (await db_client.post(url, json={})).status_code == 401
    now = await db_client.post(url, json={}, headers=ADMIN)
    given = await db_client.post(url, json={"at": at.isoformat()}, headers=ADMIN)

    assert now.status_code == 200
    assert abs(datetime.fromisoformat(now.json()["gun_start_at"]) - datetime.now(UTC)) < timedelta(
        seconds=5
    )
    assert given.json()["gun_start_at"] == "2027-03-06T06:31:12Z"
    missing = await db_client.post(
        "/api/v1/admin/categories/999999/gun-start", json={}, headers=ADMIN
    )
    assert missing.json()["code"] == "CATEGORY_NOT_FOUND"


async def test_mark_and_undo_dnf(db_client, race, field):
    bib = field["chi"].bib_number

    marked = await db_client.post(f"/api/v1/admin/runners/{bib}/dnf", headers=ADMIN)
    after_dnf = (await db_client.get(RESULTS, params={"category": "HALF"})).json()["items"]
    undone = await db_client.delete(f"/api/v1/admin/runners/{bib}/dnf", headers=ADMIN)
    after_undo = (await db_client.get(RESULTS, params={"category": "HALF"})).json()["items"]

    assert marked.json() == {"bib_number": bib, "status": "dnf"}
    assert after_dnf[-1]["full_name"] in ("Chi Test", "Dayo Test")
    assert {i["full_name"]: i["status"] for i in after_dnf}["Chi Test"] == "dnf"
    assert undone.json()["status"] == "registered"
    assert {i["full_name"]: i["status"] for i in after_undo}["Chi Test"] == "started"


async def test_rebuilds_happen_at_most_every_few_seconds(session, redis, race, field, monkeypatch):
    monkeypatch.setattr(timing, "MIN_REBUILD_S", 3)
    first = await timing.standings(session, redis, race.half)
    await race.scan(field["chi"], "FINISH", 80)
    await timing.mark_changed(redis, {race.half.id})

    soon = await timing.standings(session, redis, race.half)
    await redis.delete(f"standings:{race.half.id}:recent")  # 3 s later
    later = await timing.standings(session, redis, race.half)

    assert soon == first
    assert later[0].full_name == "Chi Test"
