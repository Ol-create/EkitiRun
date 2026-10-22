import asyncio
import hashlib
import hmac
import json
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.core.errors import AppError
from app.models import Payment, Pledge, Sponsor
from app.modules.payments import service
from app.modules.payments.gateway import (
    FakeGateway,
    GatewayError,
    PaystackGateway,
    VerifiedTransaction,
)

WEBHOOK = "/api/v1/webhooks/paystack"
SECRET = "sk_test_secret_for_tests"
AMOUNT = 200_000_000  # ₦2,000,000


class ScriptedGateway:
    """Answers verify() with whatever the test sets, and counts the calls."""

    def __init__(self, status="success", amount=AMOUNT, currency="NGN", error=False):
        self.status, self.amount, self.currency, self.error = status, amount, currency, error
        self.verify_calls = 0

    async def initialize(self, reference, amount_kobo, email, metadata):
        raise NotImplementedError

    async def verify(self, reference):
        self.verify_calls += 1
        await asyncio.sleep(0)  # let concurrent callers interleave
        if self.error:
            raise GatewayError("down")
        return VerifiedTransaction(
            reference=reference,
            status=self.status,
            amount_kobo=self.amount,
            currency=self.currency,
            paid_at=datetime(2027, 1, 10, 9, 30, tzinfo=UTC) if self.status == "success" else None,
            raw={"id": 1, "status": self.status},
        )


@pytest.fixture(autouse=True)
def paystack_secret(monkeypatch):
    monkeypatch.setattr(settings, "paystack_secret_key", SECRET)


@pytest.fixture
def gateway(monkeypatch) -> ScriptedGateway:
    scripted = ScriptedGateway()
    monkeypatch.setattr(service, "get_gateway", lambda: scripted)
    return scripted


async def make_pledge(session, status="pending", email="finance@acme.ng") -> Pledge:
    sponsor = Sponsor(
        company_name="Acme Ltd", contact_name="Bola Ade", email=email, phone="+2348031234567"
    )
    session.add(sponsor)
    await session.flush()
    pledge = Pledge(
        sponsor_id=sponsor.id,
        amount_kobo=AMOUNT,
        reference=service.new_reference(),
        status=status,
    )
    session.add(pledge)
    await session.flush()
    return pledge


def signed(event: str, reference: str, secret: str = SECRET) -> tuple[bytes, dict]:
    body = json.dumps({"event": event, "data": {"reference": reference, "amount": AMOUNT}}).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha512).hexdigest()
    return body, {"x-paystack-signature": signature, "content-type": "application/json"}


async def payments_for(session, pledge) -> list[Payment]:
    return list(await session.scalars(select(Payment).where(Payment.pledge_id == pledge.id)))


# ---------------------------------------------------------------- Paystack API calls


async def test_start_checkout_sends_the_right_request():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        data = {"authorization_url": "https://checkout.paystack.com/abc", "reference": "EKR-1"}
        return httpx.Response(200, json={"status": True, "data": data})

    gateway = PaystackGateway(SECRET, "https://paystack.test", httpx.MockTransport(handler))
    pledge = Pledge(reference="EKR-1", amount_kobo=AMOUNT, sponsor_id=None)

    checkout = await service.start_checkout(pledge, "finance@acme.ng", gateway)

    assert checkout.authorization_url == "https://checkout.paystack.com/abc"
    assert seen["auth"] == f"Bearer {SECRET}"
    assert seen["url"] == "https://paystack.test/transaction/initialize"
    body = seen["body"]
    assert body["reference"] == "EKR-1"
    assert body["amount"] == AMOUNT
    assert body["currency"] == "NGN"
    assert body["email"] == "finance@acme.ng"
    assert "bank_transfer" in body["channels"]
    assert body["callback_url"].endswith("/sponsors/thank-you")


async def test_start_checkout_provider_error_is_502():
    down = httpx.MockTransport(lambda r: httpx.Response(500, json={"status": False}))
    gateway = PaystackGateway(SECRET, "https://paystack.test", down)

    with pytest.raises(AppError) as exc:
        await service.start_checkout(Pledge(reference="EKR-1", amount_kobo=1), "a@b.ng", gateway)

    assert exc.value.status_code == 502
    assert exc.value.code == "PAYMENT_PROVIDER_ERROR"


async def test_verify_parses_paystack_response():
    data = {"reference": "EKR-1", "status": "success", "amount": AMOUNT, "currency": "NGN",
            "paid_at": "2027-01-10T09:30:00.000Z"}  # fmt: skip
    ok = httpx.MockTransport(lambda r: httpx.Response(200, json={"status": True, "data": data}))

    tx = await PaystackGateway(SECRET, "https://paystack.test", ok).verify("EKR-1")

    assert (tx.status, tx.amount_kobo, tx.currency) == ("success", AMOUNT, "NGN")
    assert tx.paid_at == datetime(2027, 1, 10, 9, 30, tzinfo=UTC)


# ---------------------------------------------------------------- webhook


async def test_bad_signature_is_rejected(db_client, session, gateway):
    pledge = await make_pledge(session)
    body, headers = signed("charge.success", pledge.reference, secret="sk_test_wrong")

    response = await db_client.post(WEBHOOK, content=body, headers=headers)

    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_SIGNATURE"
    assert gateway.verify_calls == 0
    assert pledge.status == "pending"


async def test_charge_success_marks_pledge_paid(db_client, session, gateway, queued):
    pledge = await make_pledge(session)
    body, headers = signed("charge.success", pledge.reference)

    response = await db_client.post(WEBHOOK, content=body, headers=headers)

    assert response.status_code == 200
    await session.refresh(pledge)
    assert pledge.status == "paid"
    assert pledge.paid_at == datetime(2027, 1, 10, 9, 30, tzinfo=UTC)
    [payment] = await payments_for(session, pledge)
    assert (payment.event, payment.status, payment.amount_kobo) == (
        "charge.success", "success", AMOUNT,
    )  # fmt: skip
    assert queued == [("render_receipt", [str(pledge.id)])]  # E6 makes the receipt


async def test_same_webhook_twice_settles_once(db_client, session, gateway):
    pledge = await make_pledge(session)
    body, headers = signed("charge.success", pledge.reference)

    first = await db_client.post(WEBHOOK, content=body, headers=headers)
    second = await db_client.post(WEBHOOK, content=body, headers=headers)

    assert first.status_code == second.status_code == 200
    assert gateway.verify_calls == 1  # the second delivery sees `paid` and stops
    assert len(await payments_for(session, pledge)) == 1


async def test_webhook_body_is_not_trusted(db_client, session, gateway):
    """The body says success, but Paystack's own verify says failed."""
    gateway.status = "failed"
    pledge = await make_pledge(session)
    body, headers = signed("charge.success", pledge.reference)

    await db_client.post(WEBHOOK, content=body, headers=headers)

    await session.refresh(pledge)
    assert pledge.status == "failed"


async def test_wrong_amount_is_not_marked_paid(db_client, session, gateway, queued):
    gateway.amount = 100  # ₦1 paid against a ₦2m pledge
    pledge = await make_pledge(session)
    body, headers = signed("charge.success", pledge.reference)

    await db_client.post(WEBHOOK, content=body, headers=headers)

    await session.refresh(pledge)
    assert pledge.status == "pending"
    [payment] = await payments_for(session, pledge)
    assert payment.status == "amount_mismatch"
    assert queued == []


async def test_paystack_down_asks_for_a_retry(db_client, session, gateway):
    gateway.error = True
    pledge = await make_pledge(session)
    body, headers = signed("charge.success", pledge.reference)

    response = await db_client.post(WEBHOOK, content=body, headers=headers)

    assert response.status_code == 502  # Paystack retries non-2xx webhooks
    await session.refresh(pledge)
    assert pledge.status == "pending"


@pytest.mark.parametrize(
    ("event", "reference"), [("charge.success", "EKR-UNKNOWN"), ("transfer.success", "EKR-1")]
)
async def test_unknown_references_and_events_are_acknowledged(db_client, gateway, event, reference):
    body, headers = signed(event, reference)

    response = await db_client.post(WEBHOOK, content=body, headers=headers)

    assert response.status_code == 200


async def test_abandoned_checkout_stays_pending(db_client, session, gateway):
    gateway.status = "abandoned"
    pledge = await make_pledge(session)
    body, headers = signed("charge.success", pledge.reference)

    await db_client.post(WEBHOOK, content=body, headers=headers)

    await session.refresh(pledge)
    assert pledge.status == "pending"
    assert await payments_for(session, pledge) == []


# ---------------------------------------------------------------- sync_pledge (status checks)


async def test_sync_pledge_settles_before_the_webhook(session, gateway):
    pledge = await make_pledge(session)

    await service.sync_pledge(session, pledge.reference)

    await session.refresh(pledge)
    assert pledge.status == "paid"


async def test_failed_then_successful_attempt_ends_paid(session, gateway):
    pledge = await make_pledge(session, status="failed")

    await service.sync_pledge(session, pledge.reference)

    await session.refresh(pledge)
    assert pledge.status == "paid"


async def test_sync_pledge_ignores_provider_outages(session, gateway):
    gateway.error = True
    pledge = await make_pledge(session)

    await service.sync_pledge(session, pledge.reference)  # must not raise

    await session.refresh(pledge)
    assert pledge.status == "pending"


async def test_fake_gateway_for_local_development(session):
    fake = FakeGateway()
    paid = await make_pledge(session)
    failed = await make_pledge(session, email="fail@acme.ng")
    for pledge, email in ((paid, "finance@acme.ng"), (failed, "fail@acme.ng")):
        checkout = await service.start_checkout(pledge, email, fake)
        assert checkout.authorization_url.endswith(f"reference={pledge.reference}")
        await service.settle(session, pledge.reference, "verify", fake)

    await session.refresh(paid)
    await session.refresh(failed)
    assert (paid.status, failed.status) == ("paid", "failed")


# ---------------------------------------------------------------- real concurrency


async def test_simultaneous_webhooks_and_checks_settle_once(engine):
    """Paystack retries plus a status check, all at the same moment."""
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        pledge = await make_pledge(s)
        await s.commit()
    gateway = ScriptedGateway()

    async def settle_in_own_session(event: str):
        async with Session() as s:
            await service.settle(s, pledge.reference, event, gateway)

    try:
        await asyncio.gather(
            *(settle_in_own_session(e) for e in ["charge.success"] * 4 + ["verify"] * 4)
        )
        async with Session() as s:
            rows = await s.scalar(
                select(func.count()).select_from(Payment).where(Payment.pledge_id == pledge.id)
            )
            status = await s.scalar(select(Pledge.status).where(Pledge.id == pledge.id))
        assert (rows, status) == (1, "paid")
    finally:
        async with Session() as s:
            await s.execute(delete(Payment).where(Payment.pledge_id == pledge.id))
            await s.execute(delete(Pledge).where(Pledge.id == pledge.id))
            await s.execute(delete(Sponsor).where(Sponsor.id == pledge.sponsor_id))
            await s.commit()
