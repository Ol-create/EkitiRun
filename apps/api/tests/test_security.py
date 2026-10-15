import json
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest

from app.core import security
from app.core.config import Settings, settings
from app.core.errors import AppError
from app.core.sms import SmsSendError, TermiiSmsSender

PHONE = "+2348031234567"


def test_verification_token_round_trip():
    token = security.create_verification_token(PHONE)
    assert security.phone_from_verification_token(token) == PHONE


@pytest.mark.parametrize(
    "token",
    [
        "not-a-token",
        # expired
        security.create_verification_token(PHONE, now=datetime.now(UTC) - timedelta(hours=1)),
        # signed with another secret
        jwt.encode({"sub": PHONE, "purpose": "phone_verification", "exp": 9999999999}, "x" * 32),
        # right secret, wrong purpose
        jwt.encode({"sub": PHONE, "purpose": "admin", "exp": 9999999999}, settings.jwt_secret),
    ],
)
def test_bad_verification_tokens_are_rejected(token):
    with pytest.raises(AppError) as exc:
        security.phone_from_verification_token(token)
    assert exc.value.status_code == 401
    assert exc.value.code == "VERIFICATION_INVALID"


def test_otp_hash_depends_on_phone_and_code():
    h = security.hash_otp(PHONE, "123456")
    assert security.otp_matches(PHONE, "123456", h)
    assert not security.otp_matches(PHONE, "123457", h)
    assert not security.otp_matches("+2348031234568", "123456", h)


async def test_termii_sender_posts_a_dnd_sms():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"message_id": "123", "message": "Successfully Sent"})

    sender = TermiiSmsSender(
        "key", "EkitiRun", "https://termii.test/", httpx.MockTransport(handler)
    )
    await sender.send(PHONE, "hello")

    assert seen["url"] == "https://termii.test/api/sms/send"
    assert seen["body"] == {
        "api_key": "key",
        "to": "2348031234567",
        "from": "EkitiRun",
        "sms": "hello",
        "type": "plain",
        "channel": "dnd",
    }


async def test_termii_errors_raise_sms_send_error():
    rejected = httpx.MockTransport(lambda r: httpx.Response(400, json={"message": "bad"}))
    sender = TermiiSmsSender("key", "EkitiRun", "https://termii.test", rejected)
    with pytest.raises(SmsSendError):
        await sender.send(PHONE, "hello")


def test_production_refuses_unsafe_settings():
    with pytest.raises(ValueError, match="JWT_SECRET") as exc:
        Settings(
            environment="production",
            jwt_secret="change-me",
            otp_dev_code="123456",
            sms_provider="console",
            _env_file=None,
        )
    assert "OTP_DEV_CODE" in str(exc.value)
    assert "SMS_PROVIDER=termii" in str(exc.value)


def test_production_accepts_safe_settings():
    strong = "s" * 40
    Settings(
        environment="production",
        jwt_secret=strong,
        qr_signing_secret=strong,
        gateway_secret=strong,
        otp_dev_code="",
        sms_provider="termii",
        termii_api_key="live-key",
        _env_file=None,
    )
