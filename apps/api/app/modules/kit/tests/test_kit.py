import asyncio
import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.core.errors import AppError
from app.core.security import (
    create_kit_token,
    create_qr_token,
    create_scanner_token,
    create_verification_token,
)
from app.models import Category, Checkpoint, Runner, Scan, Tracker
from app.modules.gps import ingest
from app.modules.gps.live import LIVE_KEY
from app.modules.kit import service
from app.modules.kit.schemas import KitAssignIn
from app.modules.registrations import service as registrations
from app.modules.registrations.schemas import RegistrationIn
from scripts.seed import seed

API = "/api/v1/kit"
DESK = {"Authorization": f"Bearer {create_kit_token('kit-desk-0001')}"}


async def register(session, code: str, n: int) -> Runner:
    category = await session.scalar(select(Category).where(Category.code == code))
    out = await registrations.register(
        session,
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
    return await session.get(Runner, out.runner_id)


@pytest.fixture
async def desk(session):
    """Two half marathoners and four trackers (TRK-0031 lost)."""
    await seed(session)
    ada = await register(session, "HALF", 1)
    bola = await register(session, "HALF", 2)
    session.add_all(
        [Tracker(device_id=f"8640000000000{n}", label=f"TRK-00{n}") for n in (29, 30)]
        + [
            Tracker(device_id="864000000000031", label="TRK-0031", status="lost"),
            Tracker(device_id="864000000000032", label="TRK-0032", status="returned"),
        ]
    )
    await session.flush()
    return ada, bola


def qr(runner: Runner) -> str:
    return create_qr_token(runner.bib_number, runner.id)


async def assign(client, tracker_label: str, runner: Runner | None = None, bib: str | None = None):
    body: dict[str, str | None] = {"tracker_label": tracker_label}
    body |= {"qr_token": qr(runner)} if runner else {"bib_number": bib}
    return await client.post(f"{API}/assign", json=body, headers=DESK)


async def tracker(session, label: str) -> Tracker:
    query = select(Tracker).where(Tracker.label == label)
    return await session.scalar(query.execution_options(populate_existing=True))


# ---------------------------------------------------------------- login


async def test_kit_pin_login(db_client):
    login = {"pin": settings.kit_pin, "device_id": "kit-desk-1"}
    ok = await db_client.post(f"{API}/login", json=login)
    wrong = await db_client.post(f"{API}/login", json=login | {"pin": "000000"})

    assert ok.status_code == 200
    unlocked = {"Authorization": f"Bearer {ok.json()['token']}"}
    assert (await db_client.get(f"{API}/outstanding", headers=unlocked)).status_code == 200
    assert (wrong.status_code, wrong.json()["code"]) == (401, "PIN_INVALID")


async def test_wrong_pins_share_the_scanner_limit(client):
    for _ in range(10):
        await client.post(f"{API}/login", json={"pin": "000000", "device_id": "kit-desk-1"})

    response = await client.post(
        f"{API}/login", json={"pin": settings.kit_pin, "device_id": "kit-desk-1"}
    )

    assert response.json()["code"] == "PIN_RATE_LIMITED"


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": f"Bearer {create_scanner_token('phone', 1)}"}],
)
async def test_kit_endpoints_need_a_kit_login(client, headers):
    response = await client.get(f"{API}/outstanding", headers=headers)

    assert (response.status_code, response.json()["code"]) == (401, "KIT_AUTH_REQUIRED")


# ---------------------------------------------------------------- hand out


async def test_hand_out_by_qr(db_client, session, desk):
    ada, _ = desk

    response = await assign(db_client, "trk-29", ada)

    assert response.status_code == 200
    assert response.json() == {
        "bib_number": ada.bib_number,
        "full_name": "Runner 1",
        "category_code": "HALF",
        "tracker_label": "TRK-0029",
        "already_assigned": False,
    }
    t = await tracker(session, "TRK-0029")
    assert (t.status, t.runner_id) == ("assigned", ada.id)
    await session.refresh(ada)
    assert ada.kit_collected_at is not None


@pytest.mark.parametrize("label", ["30", "TRK-0030", "trk0030", "864000000000030"])
async def test_tracker_can_be_named_many_ways(db_client, desk, label):
    ada, _ = desk

    response = await assign(db_client, label, ada)

    assert response.json()["tracker_label"] == "TRK-0030"


async def test_hand_out_by_typed_bib(db_client, desk):
    ada, _ = desk

    response = await assign(db_client, "29", bib=ada.bib_number.lower().replace("000", ""))

    assert response.json()["bib_number"] == ada.bib_number


async def test_scanning_the_same_pair_again_is_harmless(db_client, desk):
    ada, _ = desk
    await assign(db_client, "29", ada)

    again = await assign(db_client, "29", ada)

    assert again.status_code == 200
    assert again.json()["already_assigned"] is True


async def test_a_returned_tracker_can_go_out_again(db_client, desk):
    ada, _ = desk

    response = await assign(db_client, "TRK-0032", ada)

    assert response.status_code == 200


async def test_hand_out_errors(db_client, desk):
    ada, bola = desk
    await assign(db_client, "29", ada)

    cases = {
        "TRACKER_IN_USE": await assign(db_client, "29", bola),
        "RUNNER_HAS_TRACKER": await assign(db_client, "30", ada),
        "TRACKER_LOST": await assign(db_client, "31", bola),
        "TRACKER_NOT_FOUND": await assign(db_client, "TRK-0999", bola),
        "RUNNER_NOT_FOUND": await assign(db_client, "30", bib="H0999"),
    }
    forged = await db_client.post(
        f"{API}/assign",
        json={"tracker_label": "30", "qr_token": qr(bola).replace(bola.bib_number, "H0999")},
        headers=DESK,
    )
    both = await db_client.post(
        f"{API}/assign",
        json={"tracker_label": "30", "qr_token": qr(bola), "bib_number": bola.bib_number},
        headers=DESK,
    )

    assert {code: r.json()["code"] for code, r in cases.items()} == {c: c for c in cases}
    assert ada.bib_number in cases["TRACKER_IN_USE"].json()["detail"]
    assert forged.json()["code"] == "QR_INVALID"
    assert both.status_code == 422


# ---------------------------------------------------------------- returns and the list


async def test_return(db_client, session, redis, desk):
    ada, _ = desk
    await assign(db_client, "29", ada)
    await redis.hset(LIVE_KEY, str(ada.id), "{}")  # a dot on the live map

    returned = await db_client.post(f"{API}/return", json={"tracker_label": "29"}, headers=DESK)
    again = await db_client.post(f"{API}/return", json={"tracker_label": "29"}, headers=DESK)

    assert returned.json() == {
        "bib_number": ada.bib_number,
        "full_name": "Runner 1",
        "tracker_label": "TRK-0029",
    }
    t = await tracker(session, "TRK-0029")
    assert (t.status, t.runner_id) == ("returned", None)
    assert await redis.hget(LIVE_KEY, str(ada.id)) is None
    assert (again.status_code, again.json()["code"]) == (409, "TRACKER_NOT_ASSIGNED")


async def test_outstanding_list(db_client, session, desk):
    ada, bola = desk
    await assign(db_client, "29", ada)
    await assign(db_client, "30", bola)
    half = await session.scalar(select(Category).where(Category.code == "HALF"))
    finish = await session.scalar(
        select(Checkpoint).where(Checkpoint.route_id == half.route_id, Checkpoint.is_finish)
    )
    session.add(Scan(client_id=uuid.uuid4(), runner_id=ada.id, checkpoint_id=finish.id,
                     device_id="p", scanned_at=datetime.now(UTC)))  # fmt: skip
    await session.flush()

    body = (await db_client.get(f"{API}/outstanding", headers=DESK)).json()

    assert body["out"] == 2
    assert [(t["tracker_label"], t["race_status"]) for t in body["trackers"]] == [
        ("TRK-0029", "finished"),  # should hand it back
        ("TRK-0030", "registered"),
    ]


async def test_gps_writer_picks_up_new_assignments(db_client, session, desk):
    ada, _ = desk
    index = ingest.TrackerIndex()
    await index.refresh(session, force=True)
    assert "864000000000029" not in index.by_device

    await assign(db_client, "29", ada)
    await index.refresh(session, force=True)

    assert index.by_device["864000000000029"].bib_number == ada.bib_number


# ---------------------------------------------------------------- two desks at once


async def test_two_desks_cannot_hand_out_one_tracker(engine):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    tag = uuid.uuid4().hex[:6]
    async with Session() as s:
        category = (await s.scalars(select(Category).limit(1))).first()
        if category is None:
            await seed(s)
            await s.commit()
            category = (await s.scalars(select(Category).limit(1))).first()
        runners = [
            Runner(category_id=category.id, bib_number=f"Y{tag[:2]}{i}", first_name="A",
                   last_name=str(i), gender="F", date_of_birth=date(1990, 1, 1),
                   phone=f"+23480{int(tag, 16) % 10**7:07d}{i}", emergency_contact_name="C D",
                   emergency_contact_phone="+2348000000000", tracking_consent_at=datetime.now(UTC))
            for i in range(2)
        ]  # fmt: skip
        shared = Tracker(device_id=f"dev-{tag}", label=f"T-{tag.upper()}")  # labels are upper-case
        s.add_all([*runners, shared])
        await s.commit()

    async def hand_out(runner):
        async with Session() as s:
            try:
                return await service.assign(
                    s, KitAssignIn(qr_token=qr(runner), tracker_label=shared.label)
                )
            except AppError as exc:
                return exc.code

    try:
        results = await asyncio.gather(*(hand_out(r) for r in runners))
        assert sorted(r if isinstance(r, str) else "ok" for r in results) == [
            "TRACKER_IN_USE",
            "ok",
        ]
    finally:
        async with Session() as s:
            await s.execute(delete(Tracker).where(Tracker.id == shared.id))
            await s.execute(delete(Runner).where(Runner.id.in_([r.id for r in runners])))
            await s.commit()
