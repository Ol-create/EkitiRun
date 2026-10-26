import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.broadcast import broadcaster
from app.core.security import (
    create_admin_token,
    create_qr_token,
    create_scanner_token,
    create_verification_token,
)
from app.models import Category, Checkpoint, Runner, Scan, ScanCorrection
from app.modules.registrations import service as registrations
from app.modules.registrations.schemas import RegistrationIn
from app.modules.results.schemas import SCANS_CHANNEL
from scripts import create_admin
from scripts.seed import seed

GUN = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=3)  # the race was this morning
FINISH_AT = GUN + timedelta(minutes=95, seconds=30)
PAST = (GUN + timedelta(minutes=60)).isoformat()


@pytest.fixture
async def race(session):
    """A half marathoner (H0001) with a phone scan at 10 km, an organiser, their token."""
    await seed(session)
    half = await session.scalar(select(Category).where(Category.code == "HALF"))
    half.gun_start_at = GUN
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
    runner = await session.get(Runner, out.runner_id)
    cps = {
        cp.code: cp
        for cp in await session.scalars(
            select(Checkpoint).where(Checkpoint.route_id == half.route_id)
        )
    }
    session.add(Scan(client_id=uuid.uuid4(), runner_id=runner.id, checkpoint_id=cps["CP10"].id,
                     device_id="phone-cp10", scanned_at=GUN + timedelta(minutes=50)))  # fmt: skip
    admin = await create_admin.create(session, "office@ekitirun.ng", "Race Office", "x" * 16)
    await session.flush()
    headers = {"Authorization": f"Bearer {create_admin_token(admin.id, admin.session_version)}"}
    return runner, cps, headers


def url(bib: str, checkpoint_id: int | None = None) -> str:
    base = f"/api/v1/admin/runners/{bib}/scans"
    return base if checkpoint_id is None else f"{base}/{checkpoint_id}"


async def results(client) -> list[dict]:
    return (await client.get("/api/v1/results", params={"category": "HALF"})).json()["items"]


async def history(session, runner) -> list[ScanCorrection]:
    query = select(ScanCorrection).where(ScanCorrection.runner_id == runner.id)
    return list(await session.scalars(query.order_by(ScanCorrection.id)))


async def test_add_a_missing_finish_time_from_the_paper_sheet(db_client, session, race):
    runner, cps, headers = race
    body = {"scanned_at": FINISH_AT.isoformat(), "reason": "Finish paper sheet, line 14"}

    response = await db_client.put(url("h1", cps["FINISH"].id), json=body, headers=headers)

    assert response.status_code == 200
    out = response.json()
    assert out["action"] == "add"
    assert out["checkpoint"]["entry"] == "office"
    assert out["checkpoint"]["elapsed_seconds"] == 95 * 60 + 30
    [top] = await results(db_client)
    assert (top["status"], top["finish_seconds"]) == ("finished", 95 * 60 + 30)
    [audit] = await history(session, runner)
    assert (audit.action, audit.previous, audit.admin_name) == ("add", None, "Race Office")
    assert audit.reason == "Finish paper sheet, line 14"


async def test_correct_a_phone_time_and_keep_the_original(db_client, session, race):
    runner, cps, headers = race
    later = GUN + timedelta(minutes=52)  # later than the phone said: earliest-wins doesn't apply

    response = await db_client.put(
        url(runner.bib_number, cps["CP10"].id),
        json={"scanned_at": later.isoformat(), "reason": "Phone clock was 2 minutes fast"},
        headers=headers,
    )

    assert response.json()["action"] == "correct"
    [audit] = await history(session, runner)
    assert audit.previous["device_id"] == "phone-cp10"
    assert audit.previous["corrected_at"] == (GUN + timedelta(minutes=50)).isoformat()
    assert audit.new["corrected_at"] == later.isoformat()
    [item] = await results(db_client)
    assert item["elapsed_seconds"] == 52 * 60


async def test_phone_uploads_never_overwrite_an_office_time(db_client, race):
    runner, cps, headers = race
    office_time = GUN + timedelta(minutes=55)
    await db_client.put(url(runner.bib_number, cps["CP10"].id),
                        json={"scanned_at": office_time.isoformat(), "reason": "Paper sheet"},
                        headers=headers)  # fmt: skip

    earlier = GUN + timedelta(minutes=40)
    qr = create_qr_token(runner.bib_number, runner.id)
    scan = {"client_id": str(uuid.uuid4()), "qr_token": qr, "scanned_at": earlier.isoformat()}
    phone = {"Authorization": f"Bearer {create_scanner_token('phone-late', cps['CP10'].id)}"}
    upload = await db_client.post(
        "/api/v1/scans/batch",
        json={"device_id": "phone-late", "checkpoint_id": cps["CP10"].id, "scans": [scan]},
        headers=phone,
    )

    assert upload.json()["results"][0]["status"] == "duplicate"
    [item] = await results(db_client)
    assert item["elapsed_seconds"] == 55 * 60


async def test_remove_a_wrong_scan(db_client, session, race):
    runner, cps, headers = race

    response = await db_client.delete(
        url(runner.bib_number, cps["CP10"].id),
        params={"reason": "Scanned at the wrong checkpoint"},
        headers=headers,
    )

    assert response.json()["checkpoint"]["scanned_at"] is None
    assert await session.scalar(select(Scan).where(Scan.runner_id == runner.id)) is None
    [audit] = await history(session, runner)
    assert (audit.action, audit.new) == ("remove", None)
    assert audit.previous["device_id"] == "phone-cp10"
    again = {"reason": "again please"}
    missing = await db_client.delete(
        url(runner.bib_number, cps["CP10"].id), params=again, headers=headers
    )
    assert missing.json()["code"] == "SCAN_NOT_FOUND"


async def test_runner_times_and_history(db_client, race):
    runner, cps, headers = race
    for minutes, reason in ((51, "first fix"), (52, "second fix")):
        await db_client.put(url(runner.bib_number, cps["CP10"].id),
                            json={"scanned_at": (GUN + timedelta(minutes=minutes)).isoformat(),
                                  "reason": reason}, headers=headers)  # fmt: skip

    body = (await db_client.get(url(runner.bib_number), headers=headers)).json()

    assert (body["bib_number"], body["full_name"], body["status"]) == (
        "H0001",
        "Ada Okafor",
        "started",
    )
    by_code = {c["checkpoint_code"]: c for c in body["checkpoints"]}
    assert list(by_code) == ["START", "CP5", "CP10", "CP15", "CP20", "FINISH"]
    assert by_code["CP10"]["entry"] == "office"
    assert by_code["FINISH"]["scanned_at"] is None
    assert [h["reason"] for h in body["history"]] == ["second fix", "first fix"]


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"scanned_at": PAST, "reason": "no"}, "VALIDATION_ERROR"),
        ({"scanned_at": PAST[:19], "reason": "no time zone"}, "VALIDATION_ERROR"),
        ({"scanned_at": "2099-01-01T09:00:00+01:00", "reason": "far future"}, "TIME_IN_FUTURE"),
    ],
)
async def test_rejected_times(db_client, race, body, code):
    runner, cps, headers = race

    response = await db_client.put(
        url(runner.bib_number, cps["CP10"].id), json=body, headers=headers
    )

    assert response.json()["code"] == code


async def test_wrong_course_unknown_runner_and_no_admin(db_client, session, race):
    runner, cps, headers = race
    full = await session.scalar(select(Category).where(Category.code == "FULL"))
    full_cp = await session.scalar(select(Checkpoint).where(Checkpoint.route_id == full.route_id))
    body = {"scanned_at": PAST, "reason": "paper sheet"}

    wrong = await db_client.put(url(runner.bib_number, full_cp.id), json=body, headers=headers)
    unknown = await db_client.put(url("H0999", cps["CP10"].id), json=body, headers=headers)
    anonymous = await db_client.put(url(runner.bib_number, cps["CP10"].id), json=body)

    assert wrong.json()["code"] == "WRONG_COURSE"
    assert unknown.json()["code"] == "RUNNER_NOT_FOUND"
    assert anonymous.status_code == 401


async def test_corrections_are_announced_live(db_client, redis, race):
    runner, cps, headers = race
    async with broadcaster(redis, SCANS_CHANNEL).listen(SCANS_CHANNEL) as messages:
        await db_client.put(url(runner.bib_number, cps["FINISH"].id),
                            json={"scanned_at": FINISH_AT.isoformat(), "reason": "Paper sheet"},
                            headers=headers)  # fmt: skip
        event = await asyncio.wait_for(anext(messages), 2)

    assert (event["bib_number"], event["checkpoint_name"]) == ("H0001", "Finish")


async def test_dev_token_is_recorded_as_such(db_client, session, race):
    runner, cps, _ = race

    await db_client.put(url(runner.bib_number, cps["CP10"].id),
                        json={"scanned_at": (GUN + timedelta(minutes=51)).isoformat(),
                              "reason": "testing locally"},
                        headers={"Authorization": "Bearer dev-admin"})  # fmt: skip

    [audit] = await history(session, runner)
    assert (audit.admin_id, audit.admin_name) == (None, "Development token")
