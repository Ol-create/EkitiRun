"""Live updates over Redis pub/sub and Server-Sent Events (E11)."""

import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core import broadcast
from app.core.broadcast import broadcaster, publish
from app.core.security import create_qr_token, create_scanner_token, create_verification_token
from app.models import Category, Checkpoint
from app.modules.registrations import service as registrations
from app.modules.registrations.schemas import RegistrationIn
from app.modules.results import service as results
from scripts.seed import seed

GUN = datetime(2027, 3, 6, 6, 30, tzinfo=UTC)


async def next_message(messages, timeout=2.0):
    return await asyncio.wait_for(anext(messages), timeout)


# ---------------------------------------------------------------- broadcaster


async def test_every_listener_gets_each_message(redis):
    hub = broadcaster(redis, "scans")
    async with hub.listen("scans") as a, hub.listen("scans") as b:
        await publish(redis, "scans", {"n": 1})

        assert await next_message(a) == {"n": 1}
        assert await next_message(b) == {"n": 1}


async def test_pattern_channels_only_reach_their_listeners(redis):
    hub = broadcaster(redis, "positions:*")
    async with hub.listen("positions:H0001") as one, hub.listen("positions:H0002") as two:
        await publish(redis, "positions:H0002", {"bib": "H0002"})
        await publish(redis, "positions:H0001", {"bib": "H0001"})

        assert await next_message(one) == {"bib": "H0001"}
        assert await next_message(two) == {"bib": "H0002"}


async def test_a_slow_listener_misses_messages_but_never_blocks(redis, monkeypatch):
    monkeypatch.setattr(broadcast, "QUEUE_SIZE", 2)
    hub = broadcaster(redis, "scans")
    async with hub.listen("scans") as slow, hub.listen("scans") as fast:
        for n in range(5):
            await publish(redis, "scans", {"n": n})
            assert await next_message(fast) == {"n": n}

        assert [await next_message(slow), await next_message(slow)] == [{"n": 0}, {"n": 1}]
        with pytest.raises(TimeoutError):
            await next_message(slow, timeout=0.2)  # 2..4 were dropped for this one


async def test_last_listener_leaving_drops_the_redis_subscription(redis):
    hub = broadcaster(redis, "scans")
    async with hub.listen("scans"):
        task = hub.task
        assert task is not None and not task.done()

    await asyncio.sleep(0)
    assert hub.task is None
    assert task.cancelled() or task.done()


# ---------------------------------------------------------------- /stream/results


def event(bib: str, category: str) -> dict:
    return {
        "bib_number": bib,
        "category_code": category,
        "checkpoint_id": 7,
        "checkpoint_name": "10 km",
        "distance_km": 10.0,
        "scanned_at": "2027-03-06T07:20:00Z",
        "elapsed_seconds": 3000,
    }


async def test_scan_stream_can_follow_one_race(redis):
    stream = results.scan_events(redis, "half")
    first = asyncio.create_task(anext(stream))
    await asyncio.sleep(0.05)  # let the stream subscribe

    await publish(redis, "scans", event("F0001", "FULL"))
    await publish(redis, "scans", event("H0001", "HALF"))

    received = await asyncio.wait_for(first, 2)
    assert (received.bib_number, received.category_code) == ("H0001", "HALF")
    await stream.aclose()


async def test_uploaded_scans_are_announced_live(db_client, session, redis):
    await seed(session)
    half = await session.scalar(select(Category).where(Category.code == "HALF"))
    half.gun_start_at = GUN
    cp10 = await session.scalar(
        select(Checkpoint).where(Checkpoint.route_id == half.route_id, Checkpoint.code == "CP10")
    )
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
    stream = results.scan_events(redis, None)
    first = asyncio.create_task(anext(stream))
    await asyncio.sleep(0.05)

    upload = await db_client.post(
        "/api/v1/scans/batch",
        json={
            "device_id": "phone-cp10",
            "checkpoint_id": cp10.id,
            "scans": [
                {
                    "client_id": str(uuid.uuid4()),
                    "qr_token": create_qr_token(out.bib_number, out.runner_id),
                    "scanned_at": (GUN + timedelta(minutes=50)).isoformat(),
                }
            ],
        },
        headers={"Authorization": f"Bearer {create_scanner_token('phone-cp10', cp10.id)}"},
    )
    assert upload.json()["results"][0]["status"] == "accepted"

    received = await asyncio.wait_for(first, 2)
    assert received.model_dump(mode="json") == {
        "bib_number": "H0001",
        "category_code": "HALF",
        "checkpoint_id": cp10.id,
        "checkpoint_name": "10 km",
        "distance_km": 10.0,
        "scanned_at": "2027-03-06T07:20:00Z",
        "elapsed_seconds": 50 * 60,
    }
    await stream.aclose()
