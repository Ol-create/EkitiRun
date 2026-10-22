import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.security import create_scanner_token, create_verification_token, hash_pin
from app.models import Category, Checkpoint
from app.modules.registrations import service as registrations
from app.modules.registrations.schemas import RegistrationIn
from scripts.seed import seed

API = "/api/v1/scanner"
DEVICE = "phone-test-0001"


@pytest.fixture
async def course(session):
    """Seeded courses, with PIN 482913 on the half marathon's 10 km checkpoint."""
    await seed(session)
    half = await session.scalar(select(Category).where(Category.code == "HALF"))
    cp10 = await session.scalar(
        select(Checkpoint).where(Checkpoint.route_id == half.route_id, Checkpoint.code == "CP10")
    )
    cp10.pin_hash = hash_pin("482913")
    await session.flush()
    return half, cp10


async def register(session, category: Category, phone: str, first: str):
    body = RegistrationIn(
        verification_token=create_verification_token(phone),
        first_name=first,
        last_name="Okafor",
        gender="F",
        date_of_birth=date(1990, 1, 1),
        category_id=category.id,
        emergency_contact_name="Chidi Okafor",
        emergency_contact_phone="+2348099998888",
        tracking_consent=True,
    )
    return await registrations.register(session, body)


async def login(client, pin="482913"):
    return await client.post(f"{API}/login", json={"pin": pin, "device_id": DEVICE})


async def test_pin_login_binds_the_phone_to_its_checkpoint(db_client, course):
    _, cp10 = course

    response = await login(db_client)

    assert response.status_code == 200
    body = response.json()
    assert body["checkpoint"] == {
        "id": cp10.id,
        "code": "CP10",
        "name": "10 km",
        "distance_km": 10.0,
        "is_start": False,
        "is_finish": False,
        "category_codes": ["HALF"],
    }
    expires = datetime.fromisoformat(body["expires_at"])
    assert timedelta(hours=23) < expires - datetime.now(UTC) <= timedelta(hours=24)


async def test_wrong_pin(db_client, course):
    response = await login(db_client, pin="000001")

    assert response.status_code == 401
    assert response.json()["code"] == "PIN_INVALID"


async def test_wrong_pins_are_rate_limited(db_client, course):
    for _ in range(10):
        await login(db_client, pin="111111")

    response = await login(db_client)  # even the right PIN waits now

    assert response.status_code == 429
    assert response.json()["code"] == "PIN_RATE_LIMITED"


async def test_roster_lists_runners_on_this_course_only(db_client, session, course):
    half, _ = course
    full = await session.scalar(select(Category).where(Category.code == "FULL"))
    await register(session, half, "+2348031234501", "Ada")
    await register(session, full, "+2348031234502", "Bisi")
    token = (await login(db_client)).json()["token"]

    response = await db_client.get(f"{API}/roster", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    runners = response.json()["runners"]
    assert [(r["bib_number"], r["full_name"], r["category_code"]) for r in runners] == [
        ("H0001", "Ada Okafor", "HALF")
    ]
    assert set(runners[0]) == {"runner_id", "bib_number", "full_name", "category_code"}


@pytest.mark.parametrize(
    "authorization",
    [
        None,
        "Bearer not-a-token",
        f"Bearer {create_verification_token('+2348031234567')}",  # a phone token, not a scanner
    ],
)
async def test_roster_needs_a_scanner_login(db_client, authorization):
    headers = {"Authorization": authorization} if authorization else {}

    response = await db_client.get(f"{API}/roster", headers=headers)

    assert response.status_code == 401
    assert response.json()["code"] == "SCANNER_AUTH_REQUIRED"


async def test_scans_are_only_accepted_for_the_logged_in_checkpoint(db_client, course):
    _, cp10 = course
    token = create_scanner_token(DEVICE, cp10.id)
    scan = {
        "client_id": str(uuid.uuid4()),
        "qr_token": "H0004",
        "scanned_at": "2027-03-06T07:00:00Z",
    }
    headers = {"Authorization": f"Bearer {token}"}

    own = await db_client.post(
        "/api/v1/scans/batch",
        json={"device_id": DEVICE, "checkpoint_id": cp10.id, "scans": [scan]},
        headers=headers,
    )
    other = await db_client.post(
        "/api/v1/scans/batch",
        json={"device_id": DEVICE, "checkpoint_id": cp10.id + 1, "scans": [scan]},
        headers=headers,
    )
    anonymous = await db_client.post(
        "/api/v1/scans/batch",
        json={"device_id": DEVICE, "checkpoint_id": cp10.id, "scans": [scan]},
    )

    assert own.status_code == 200
    assert other.status_code == 403
    assert other.json()["code"] == "WRONG_CHECKPOINT"
    assert anonymous.status_code == 401


async def test_pin_script_sets_unique_pins(session, course, monkeypatch, capsys):
    from scripts import checkpoint_pins

    class SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(checkpoint_pins, "SessionLocal", SessionContext)

    await checkpoint_pins.main(reset_all=False)

    lines = capsys.readouterr().out.splitlines()
    rows = [line.split(",") for line in lines[1:] if line.count(",") == 3]
    assert len(rows) == 20  # 21 checkpoints, one already had a PIN
    pins = [row[3] for row in rows]
    assert len(set(pins)) == len(pins)
    first = await session.scalar(select(Checkpoint).where(Checkpoint.pin_hash == hash_pin(pins[0])))
    assert first is not None
