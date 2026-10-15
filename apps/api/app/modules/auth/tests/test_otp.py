from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.core import security
from app.core.config import settings
from app.models import OtpCode

API = "/api/v1/auth/otp"
PHONE = "+2348031234567"


@pytest.fixture(autouse=True)
def random_codes(monkeypatch):
    """Use real random codes, not the development shortcut code."""
    monkeypatch.setattr(settings, "otp_dev_code", None)


async def request_code(client, phone=PHONE):
    return await client.post(f"{API}/request", json={"phone": phone})


async def verify(client, code, phone=PHONE):
    return await client.post(f"{API}/verify", json={"phone": phone, "code": code})


async def test_request_texts_a_code_and_stores_only_a_hash(db_client, session, sms):
    response = await request_code(db_client)

    assert response.status_code == 204
    code = sms.last_code_for(PHONE)
    assert "EkitiRun verification code" in sms.sent[-1][1]
    stored = (await session.scalars(select(OtpCode).where(OtpCode.phone == PHONE))).all()
    assert len(stored) == 1
    assert code not in stored[0].code_hash


async def test_correct_code_returns_a_verification_token(db_client, sms):
    await request_code(db_client)

    response = await verify(db_client, sms.last_code_for(PHONE))

    assert response.status_code == 200
    token = response.json()["verification_token"]
    assert security.phone_from_verification_token(token) == PHONE


async def test_a_code_works_only_once(db_client, sms):
    await request_code(db_client)
    code = sms.last_code_for(PHONE)
    assert (await verify(db_client, code)).status_code == 200

    again = await verify(db_client, code)

    assert again.status_code == 400
    assert again.json()["code"] == "OTP_INVALID"


async def test_wrong_code_counts_attempts_then_locks(db_client, sms):
    await request_code(db_client)
    code = sms.last_code_for(PHONE)
    wrong = "000000" if code != "000000" else "111111"

    first = await verify(db_client, wrong)
    assert first.status_code == 400
    assert first.json()["code"] == "OTP_INVALID"
    assert "4 attempts left" in first.json()["detail"]
    for _ in range(4):
        await verify(db_client, wrong)

    locked = await verify(db_client, code)  # even the right code is refused now

    assert locked.status_code == 429
    assert locked.json()["code"] == "OTP_TOO_MANY_ATTEMPTS"


async def test_expired_code(db_client, session, sms):
    await request_code(db_client)
    await session.execute(
        update(OtpCode).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )

    response = await verify(db_client, sms.last_code_for(PHONE))

    assert response.status_code == 400
    assert response.json()["code"] == "OTP_EXPIRED"


async def test_new_code_cancels_the_old_one(db_client, redis, sms):
    await request_code(db_client)
    old = sms.last_code_for(PHONE)
    await redis.delete(f"otp:cooldown:{PHONE}")  # skip the 60 s wait
    await request_code(db_client)
    new = sms.last_code_for(PHONE)

    if old != new:
        assert (await verify(db_client, old)).json()["code"] == "OTP_INVALID"
    assert (await verify(db_client, new)).status_code == 200


async def test_verify_without_a_request(db_client):
    response = await verify(db_client, "123456")

    assert response.status_code == 400
    assert response.json()["code"] == "OTP_INVALID"


async def test_one_request_per_phone_per_minute(db_client, sms):
    assert (await request_code(db_client)).status_code == 204

    second = await request_code(db_client)

    assert second.status_code == 429
    assert second.json()["code"] == "OTP_RATE_LIMITED"
    assert "seconds" in second.json()["detail"]
    assert len(sms.sent) == 1


async def test_ten_requests_per_ip_per_hour(db_client):
    for n in range(10):
        response = await request_code(db_client, phone=f"+23480312340{n:02d}")
        assert response.status_code == 204

    eleventh = await request_code(db_client, phone="+2348031234099")

    assert eleventh.status_code == 429
    assert eleventh.json()["code"] == "OTP_RATE_LIMITED"


async def test_sms_failure_lets_the_runner_retry(db_client, session, sms, monkeypatch):
    from app.core.sms import SmsSendError

    async def broken_send(phone, message):
        raise SmsSendError("down")

    monkeypatch.setattr(sms, "send", broken_send)
    failed = await request_code(db_client)
    assert failed.status_code == 502
    assert failed.json()["code"] == "SMS_SEND_FAILED"
    assert (await session.scalars(select(OtpCode))).all() == []

    monkeypatch.undo()
    assert (await request_code(db_client)).status_code == 204


async def test_development_shortcut_code(db_client, sms, monkeypatch):
    monkeypatch.setattr(settings, "otp_dev_code", "123456")
    await request_code(db_client)

    assert sms.last_code_for(PHONE) == "123456"
    assert (await verify(db_client, "123456")).status_code == 200
