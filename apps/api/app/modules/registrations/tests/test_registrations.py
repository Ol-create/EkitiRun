import asyncio
import io
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import segno
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.core.errors import AppError
from app.core.security import create_qr_token, create_verification_token
from app.models import Category, Route, Runner
from app.modules.registrations import service
from app.modules.registrations.schemas import RegistrationIn
from scripts.seed import seed

API = "/api/v1/registrations"
PHONE = "+2348031234567"


@pytest.fixture
async def categories(session) -> dict[str, Category]:
    await seed(session)
    rows = (await session.scalars(select(Category))).all()
    return {c.code: c for c in rows}


@pytest.fixture(autouse=True)
def race_day(monkeypatch):
    monkeypatch.setattr(settings, "race_date", date(2027, 3, 6))


def body(category_id: int, phone: str = PHONE, **overrides) -> dict:
    return {
        "verification_token": create_verification_token(phone),
        "first_name": "  Ada ",
        "last_name": "Okafor",
        "gender": "F",
        "date_of_birth": "1995-04-12",
        "email": "Ada@Example.com",
        "category_id": category_id,
        "emergency_contact_name": "Chidi Okafor",
        "emergency_contact_phone": "+2348099998888",
        "tracking_consent": True,
    } | overrides


async def test_register_saves_runner_with_next_bib(db_client, session, categories):
    half = categories["HALF"]

    first = await db_client.post(API, json=body(half.id))
    second = await db_client.post(API, json=body(half.id, phone="+2348031234568"))

    assert first.status_code == 201, first.json()
    out = first.json()
    assert out["bib_number"] == "H0001"
    assert second.json()["bib_number"] == "H0002"
    assert out["category"] == {"id": half.id, "code": "HALF", "name": "Half Marathon"}
    assert out["qr_png_url"].endswith(f"/api/v1/registrations/{out['runner_id']}/qr.png")

    runner = await session.get(Runner, uuid.UUID(out["runner_id"]))
    assert runner.phone == PHONE  # from the verified token, never from the form
    assert runner.first_name == "Ada"
    assert runner.email == "ada@example.com"
    assert runner.status == "registered"
    assert runner.tracking_consent_at is not None


async def test_bibs_are_counted_per_category(db_client, categories):
    full = await db_client.post(API, json=body(categories["FULL"].id))
    fun = await db_client.post(API, json=body(categories["FUN"].id, phone="+2348031234568"))

    assert full.json()["bib_number"] == "F0001"
    assert fun.json()["bib_number"] == "R0001"


async def test_qr_png_contains_the_signed_token(db_client, categories):
    out = (await db_client.post(API, json=body(categories["10K"].id))).json()

    response = await db_client.get(f"{API}/{out['runner_id']}/qr.png")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    expected = io.BytesIO()
    token = create_qr_token(out["bib_number"], uuid.UUID(out["runner_id"]))
    segno.make(token, error="m").save(expected, kind="png", scale=8, border=2)
    assert response.content == expected.getvalue()


async def test_qr_png_unknown_runner(db_client):
    response = await db_client.get(f"{API}/{uuid.uuid4()}/qr.png")

    assert response.status_code == 404
    assert response.json()["code"] == "RUNNER_NOT_FOUND"


async def test_one_registration_per_phone(db_client, categories):
    await db_client.post(API, json=body(categories["HALF"].id))

    again = await db_client.post(API, json=body(categories["FULL"].id))

    assert again.status_code == 409
    assert again.json()["code"] == "PHONE_ALREADY_REGISTERED"


async def test_full_category(db_client, session, categories):
    fun = categories["FUN"]
    fun.cap = 1
    await session.flush()
    await db_client.post(API, json=body(fun.id))

    response = await db_client.post(API, json=body(fun.id, phone="+2348031234568"))

    assert response.status_code == 409
    assert response.json()["code"] == "CATEGORY_FULL"


@pytest.mark.parametrize(
    ("birth", "ok"),
    [("2009-03-06", True), ("2009-03-07", False)],  # 18 exactly on race day / one day short
)
async def test_minimum_age_on_race_day(db_client, categories, birth, ok):
    response = await db_client.post(API, json=body(categories["FULL"].id, date_of_birth=birth))

    if ok:
        assert response.status_code == 201
    else:
        assert response.status_code == 422
        assert response.json()["code"] == "AGE_REQUIREMENT_NOT_MET"
        assert "18" in response.json()["detail"]


async def test_gun_start_sets_race_day(db_client, session, categories):
    full = categories["FULL"]
    full.gun_start_at = datetime(2027, 3, 13, 5, 30, tzinfo=UTC)  # a week later
    await session.flush()

    response = await db_client.post(API, json=body(full.id, date_of_birth="2009-03-10"))

    assert response.status_code == 201


async def test_fun_run_has_no_age_limit(db_client, categories):
    response = await db_client.post(
        API, json=body(categories["FUN"].id, date_of_birth="2019-01-01")
    )

    assert response.status_code == 201


@pytest.mark.parametrize(
    ("overrides", "status", "code"),
    [
        ({"tracking_consent": False}, 422, "TRACKING_CONSENT_REQUIRED"),
        ({"verification_token": "not-a-token"}, 401, "VERIFICATION_INVALID"),
        ({"date_of_birth": "2999-01-01"}, 422, "VALIDATION_ERROR"),
        ({"first_name": "   "}, 422, "VALIDATION_ERROR"),
    ],
)
async def test_rejected_registrations(db_client, categories, overrides, status, code):
    response = await db_client.post(API, json=body(categories["HALF"].id, **overrides))

    assert response.status_code == status
    assert response.json()["code"] == code


async def test_unknown_category(db_client, categories):
    response = await db_client.post(API, json=body(999_999))

    assert response.status_code == 404
    assert response.json()["code"] == "CATEGORY_NOT_FOUND"


# ---------------------------------------------------------------- real concurrency
# These use separate committed transactions (like real simultaneous requests),
# so they create and clean up their own rows.


@pytest.fixture
async def committed_category(engine):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    code = f"T{uuid.uuid4().hex[:5]}"
    async with Session() as s:
        route = Route(
            name=f"route-{code}",
            geojson={"type": "LineString", "coordinates": []},
            length_km=Decimal("5"),
        )
        s.add(route)
        await s.flush()
        cats = [
            Category(
                code=f"{code}{i}",
                name=f"Test {code}{i}",
                distance_km=Decimal("5"),
                cap=5,
                bib_prefix=chr(ord("V") + i),
                route_id=route.id,
            )
            for i in range(2)
        ]
        s.add_all(cats)
        await s.commit()
    yield Session, cats
    async with Session() as s:
        ids = [c.id for c in cats]
        await s.execute(delete(Runner).where(Runner.category_id.in_(ids)))
        await s.execute(delete(Category).where(Category.id.in_(ids)))
        await s.execute(delete(Route).where(Route.id == route.id))
        await s.commit()


async def _register(Session, category_id: int, phone: str):
    async with Session() as s:
        try:
            return await service.register(s, RegistrationIn(**body(category_id, phone=phone)))
        except AppError as exc:
            return exc.code


async def test_cap_holds_under_simultaneous_signups(committed_category):
    Session, (category, _) = committed_category
    phones = [f"+23480312{n:05d}" for n in range(20)]

    results = await asyncio.gather(*(_register(Session, category.id, p) for p in phones))

    succeeded = sorted(r.bib_number for r in results if not isinstance(r, str))
    assert succeeded == ["V0001", "V0002", "V0003", "V0004", "V0005"]
    assert [r for r in results if isinstance(r, str)] == ["CATEGORY_FULL"] * 15


async def test_same_phone_in_two_categories_at_once(committed_category):
    Session, (first, second) = committed_category

    results = await asyncio.gather(
        _register(Session, first.id, PHONE), _register(Session, second.id, PHONE)
    )

    assert sum(not isinstance(r, str) for r in results) == 1
    assert "PHONE_ALREADY_REGISTERED" in results
