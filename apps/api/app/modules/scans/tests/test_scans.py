import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.security import create_qr_token, create_scanner_token, create_verification_token
from app.models import Category, Checkpoint, Route, Runner, Scan, ScannerDevice
from app.modules.registrations import service as registrations
from app.modules.registrations.schemas import RegistrationIn
from app.modules.scans import service
from app.modules.scans.schemas import ScanBatchIn
from scripts.seed import seed

API = "/api/v1/scans/batch"
PHONE_A, PHONE_B = "phone-aaaa-0001", "phone-bbbb-0002"
T0 = datetime(2027, 3, 6, 7, 30, tzinfo=UTC)


async def register(session, category: Category, phone: str) -> Runner:
    out = await registrations.register(
        session,
        RegistrationIn(
            verification_token=create_verification_token(phone),
            first_name="Ada",
            last_name="Okafor",
            gender="F",
            date_of_birth=date(1990, 1, 1),
            category_id=category.id,
            emergency_contact_name="Chidi Okafor",
            emergency_contact_phone="+2348099998888",
            tracking_consent=True,
        ),
    )
    return await session.get(Runner, out.runner_id)


@pytest.fixture
async def race(session):
    """Seeded courses, runners H0001 (half) and F0001 (full), and the half's 10 km checkpoint."""
    await seed(session)
    cats = {c.code: c for c in await session.scalars(select(Category))}
    half_runner = await register(session, cats["HALF"], "+2348031234501")
    full_runner = await register(session, cats["FULL"], "+2348031234502")
    cp10 = await session.scalar(
        select(Checkpoint).where(
            Checkpoint.route_id == cats["HALF"].route_id, Checkpoint.code == "CP10"
        )
    )
    return half_runner, full_runner, cp10


def qr(runner: Runner) -> str:
    return create_qr_token(runner.bib_number, runner.id)


def scan(token: str, at: datetime = T0, entry: str = "qr", client_id: uuid.UUID | None = None):
    return {
        "client_id": str(client_id or uuid.uuid4()),
        "qr_token": token,
        "scanned_at": at.isoformat(),
        "entry": entry,
    }


async def upload(
    client, cp: Checkpoint, scans: list, phone=PHONE_A, sent_at: datetime | None = None
):
    body = {"device_id": phone, "checkpoint_id": cp.id, "scans": scans}
    if sent_at:
        body["sent_at"] = sent_at.isoformat()
    headers = {"Authorization": f"Bearer {create_scanner_token(phone, cp.id)}"}
    response = await client.post(API, json=body, headers=headers)
    assert response.status_code == 200, response.json()
    return response.json()["results"]


async def saved_scans(session, runner: Runner) -> list[Scan]:
    query = select(Scan).where(Scan.runner_id == runner.id)
    # populate_existing: re-read rows the API changed, not this session's stale copies
    return list(await session.scalars(query.execution_options(populate_existing=True)))


async def test_qr_scan_is_saved(db_client, session, race):
    runner, _, cp10 = race

    [result] = await upload(db_client, cp10, [scan(qr(runner))])

    assert result["status"] == "accepted"
    assert result["bib_number"] == "H0001"
    [saved] = await saved_scans(session, runner)
    assert (saved.checkpoint_id, saved.device_id, saved.entry) == (cp10.id, PHONE_A, "qr")
    assert saved.scanned_at == T0


async def test_typed_bib_is_saved_as_manual(db_client, session, race):
    runner, _, cp10 = race

    [result] = await upload(db_client, cp10, [scan("h1", entry="manual")])

    assert (result["status"], result["bib_number"]) == ("accepted", "H0001")
    [saved] = await saved_scans(session, runner)
    assert saved.entry == "manual"


@pytest.mark.parametrize(
    ("make_token", "entry", "reason"),
    [
        (lambda h, f: qr(h).replace("H0001", "H0002"), "qr", "bad_qr"),  # edited QR
        (lambda h, f: "H0001", "qr", "bad_qr"),  # a bare bib is not a QR token
        (lambda h, f: create_qr_token("H0001", uuid.uuid4()), "qr", "unknown_bib"),  # wrong runner
        (lambda h, f: "H0999", "manual", "unknown_bib"),
        (lambda h, f: "not a bib", "manual", "unknown_bib"),
        (lambda h, f: qr(f), "qr", "wrong_course"),  # full marathoner at a half checkpoint
    ],
)
async def test_invalid_scans(db_client, session, race, make_token, entry, reason):
    half_runner, full_runner, cp10 = race

    [result] = await upload(
        db_client, cp10, [scan(make_token(half_runner, full_runner), entry=entry)]
    )

    assert (result["status"], result["reason"]) == ("invalid", reason)
    assert await session.scalar(select(Scan.id).limit(1)) is None


async def test_retried_upload_is_a_duplicate(db_client, session, race):
    runner, _, cp10 = race
    retry = scan(qr(runner))

    first = await upload(db_client, cp10, [retry])
    again = await upload(db_client, cp10, [retry])

    assert [first[0]["status"], again[0]["status"]] == ["accepted", "duplicate"]
    assert len(await saved_scans(session, runner)) == 1


async def test_same_scan_twice_in_one_batch(db_client, session, race):
    runner, _, cp10 = race
    same = scan(qr(runner))

    results = await upload(db_client, cp10, [same, same])

    assert [r["status"] for r in results] == ["accepted", "duplicate"]


async def test_later_rescan_keeps_the_first_time(db_client, session, race):
    runner, _, cp10 = race
    await upload(db_client, cp10, [scan(qr(runner), at=T0)])

    [later] = await upload(
        db_client, cp10, [scan(qr(runner), at=T0 + timedelta(minutes=3))], PHONE_B
    )

    assert later["status"] == "duplicate"
    [saved] = await saved_scans(session, runner)
    assert (saved.scanned_at, saved.device_id) == (T0, PHONE_A)


async def test_earlier_scan_from_another_phone_wins(db_client, session, race):
    """Phone B synced late, but saw the runner first."""
    runner, _, cp10 = race
    await upload(db_client, cp10, [scan(qr(runner), at=T0)])

    [earlier] = await upload(
        db_client, cp10, [scan(qr(runner), at=T0 - timedelta(seconds=40))], PHONE_B
    )

    assert earlier["status"] == "accepted"
    [saved] = await saved_scans(session, runner)
    assert (saved.scanned_at, saved.device_id) == (T0 - timedelta(seconds=40), PHONE_B)


async def test_clock_drift_is_measured_and_corrected(db_client, session, race):
    """Phone A's clock is 5 minutes fast. Its 07:34 scan really happened at 07:29,
    before phone B's (correct) 07:30 scan, so phone A's scan is the one kept."""
    runner, _, cp10 = race
    now = datetime.now(UTC)
    await upload(db_client, cp10, [scan(qr(runner), at=T0)], PHONE_B, sent_at=now)

    [result] = await upload(
        db_client,
        cp10,
        [scan(qr(runner), at=T0 + timedelta(minutes=4))],
        PHONE_A,
        sent_at=now + timedelta(minutes=5),
    )

    assert result["status"] == "accepted"
    [saved] = await saved_scans(session, runner)
    assert saved.device_id == PHONE_A
    assert saved.clock_offset_ms == pytest.approx(-300_000, abs=5_000)
    device = await session.get(ScannerDevice, PHONE_A, populate_existing=True)
    assert device.clock_flagged
    assert device.scans_uploaded == 1


async def test_admin_device_list_flags_bad_clocks(db_client, race):
    runner, _, cp10 = race
    now = datetime.now(UTC)
    await upload(db_client, cp10, [scan(qr(runner))], PHONE_A, sent_at=now - timedelta(minutes=3))
    await upload(db_client, cp10, [scan("h1", entry="manual")], PHONE_B, sent_at=now)

    assert (await db_client.get("/api/v1/scanner/devices")).status_code == 401
    response = await db_client.get(
        "/api/v1/scanner/devices", headers={"Authorization": "Bearer dev-admin"}
    )

    devices = response.json()
    assert [d["device_id"] for d in devices] == [PHONE_A, PHONE_B]  # flagged first
    assert devices[0]["clock_flagged"] is True
    assert 170 < devices[0]["clock_offset_s"] < 190
    assert devices[1]["clock_flagged"] is False
    assert devices[0]["checkpoint_name"] == "10 km"
    assert devices[0]["category_codes"] == ["HALF"]


# ---------------------------------------------------------------- real concurrency


@pytest.fixture
async def committed_runner(engine):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    tag = uuid.uuid4().hex[:6]
    async with Session() as s:
        route = Route(name=f"route-{tag}", geojson={"type": "LineString", "coordinates": []},
                      length_km=Decimal("5"))  # fmt: skip
        s.add(route)
        await s.flush()
        category = Category(code=f"C{tag[:5]}", name=f"Test {tag}", distance_km=Decimal("5"),
                            cap=10, bib_prefix="Z", route_id=route.id)  # fmt: skip
        checkpoint = Checkpoint(route_id=route.id, code="CP1", name="1 km",
                                distance_km=Decimal("1"), lat=7.6, lng=5.2)  # fmt: skip
        s.add_all([category, checkpoint])
        await s.flush()
        runner = Runner(category_id=category.id, bib_number=f"Z{tag[:4]}"[:5], first_name="A",
                        last_name="B", gender="F", date_of_birth=date(1990, 1, 1),
                        phone=f"+23480{int(tag, 16) % 10**8:08d}", emergency_contact_name="C D",
                        emergency_contact_phone="+2348000000000",
                        tracking_consent_at=datetime.now(UTC))  # fmt: skip
        s.add(runner)
        await s.commit()
    yield Session, runner, checkpoint
    async with Session() as s:
        await s.execute(delete(Scan).where(Scan.runner_id == runner.id))
        await s.execute(delete(ScannerDevice).where(ScannerDevice.checkpoint_id == checkpoint.id))
        await s.execute(delete(Runner).where(Runner.id == runner.id))
        await s.execute(delete(Checkpoint).where(Checkpoint.id == checkpoint.id))
        await s.execute(delete(Category).where(Category.id == category.id))
        await s.execute(delete(Route).where(Route.id == route.id))
        await s.commit()


async def test_simultaneous_uploads_keep_the_earliest(committed_runner):
    Session, runner, checkpoint = committed_runner
    token = qr(runner)

    async def upload_as(phone: str, seconds: int):
        async with Session() as s:
            body = ScanBatchIn(
                device_id=phone,
                checkpoint_id=checkpoint.id,
                scans=[scan(token, at=T0 + timedelta(seconds=seconds))],
            )
            return await service.ingest_batch(s, phone, body)

    await asyncio.gather(*(upload_as(f"phone-{i:04d}-xxxx", 10 - i) for i in range(6)))

    async with Session() as s:
        rows = list(await s.scalars(select(Scan).where(Scan.runner_id == runner.id)))
    assert len(rows) == 1
    assert rows[0].scanned_at == T0 + timedelta(seconds=5)  # the earliest of 10..5 s
