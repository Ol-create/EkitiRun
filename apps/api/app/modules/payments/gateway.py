"""Talking to the payment provider. Owner: Lead (E5).

- `PaystackGateway`: the real Paystack API (test mode with sk_test_ keys).
- `FakeGateway`: local development without Paystack. Checkout goes straight to
  the thank-you page and the payment succeeds, unless the sponsor's email
  contains "fail".
"""

import hashlib
import hmac
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol

import httpx

from app.core.config import settings

# Card, bank account, USSD and "Pay with Transfer" (bank_transfer), so large
# sponsors can pay by transfer instead of hitting card limits.
CHANNELS = ["card", "bank", "ussd", "bank_transfer"]

TxStatus = Literal["success", "failed", "abandoned", "pending"]


class GatewayError(Exception):
    """The provider couldn't be reached or answered with an error. Safe to retry."""


@dataclass
class Checkout:
    reference: str
    authorization_url: str


@dataclass
class VerifiedTransaction:
    reference: str
    status: TxStatus
    amount_kobo: int
    currency: str
    paid_at: datetime | None
    raw: dict[str, Any] = field(default_factory=dict)


class PaymentGateway(Protocol):
    async def initialize(
        self, reference: str, amount_kobo: int, email: str, metadata: dict[str, Any]
    ) -> Checkout: ...

    async def verify(self, reference: str) -> VerifiedTransaction: ...


def signature_is_valid(raw_body: bytes, signature: str | None) -> bool:
    """Paystack signs each webhook body with HMAC-SHA512 of the secret key."""
    if not signature or not settings.paystack_secret_key:
        return False
    expected = hmac.new(settings.paystack_secret_key.encode(), raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature)


def _thank_you_url() -> str:
    return f"{settings.public_web_url}/sponsors/thank-you"


def _parse_time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


class PaystackGateway:
    def __init__(
        self, secret_key: str, base_url: str, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.secret_key = secret_key
        self.base_url = base_url.rstrip("/")
        self.transport = transport  # tests pass httpx.MockTransport

    async def _call(self, method: str, path: str, json: dict | None = None) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.secret_key}"}
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=15) as client:
                response = await client.request(
                    method, f"{self.base_url}{path}", json=json, headers=headers
                )
        except httpx.HTTPError as exc:
            raise GatewayError(f"Paystack unreachable: {exc}") from exc
        body = response.json() if response.content else {}
        if response.status_code >= 400 or not body.get("status"):
            raise GatewayError(f"Paystack error {response.status_code}: {body.get('message')}")
        return body["data"]

    async def initialize(
        self, reference: str, amount_kobo: int, email: str, metadata: dict[str, Any]
    ) -> Checkout:
        data = await self._call(
            "POST",
            "/transaction/initialize",
            {
                "reference": reference,
                "amount": amount_kobo,
                "currency": "NGN",
                "email": email,
                "channels": CHANNELS,
                # Paystack adds ?trxref=...&reference=... when it sends the sponsor back.
                "callback_url": _thank_you_url(),
                "metadata": metadata,
            },
        )
        return Checkout(reference=data["reference"], authorization_url=data["authorization_url"])

    async def verify(self, reference: str) -> VerifiedTransaction:
        data = await self._call("GET", f"/transaction/verify/{reference}")
        status = data.get("status")
        return VerifiedTransaction(
            reference=data.get("reference", reference),
            status=status if status in ("success", "failed", "abandoned") else "pending",
            amount_kobo=int(data.get("amount") or 0),
            currency=data.get("currency") or "",
            paid_at=_parse_time(data.get("paid_at") or data.get("paidAt")),
            raw=data,
        )


class FakeGateway:
    """In-memory stand-in for Paystack. State lives only as long as the API process."""

    def __init__(self) -> None:
        self.transactions: dict[str, dict[str, Any]] = {}

    async def initialize(
        self, reference: str, amount_kobo: int, email: str, metadata: dict[str, Any]
    ) -> Checkout:
        self.transactions[reference] = {"amount": amount_kobo, "email": email}
        return Checkout(
            reference=reference,
            authorization_url=f"{_thank_you_url()}?trxref={reference}&reference={reference}",
        )

    async def verify(self, reference: str) -> VerifiedTransaction:
        tx = self.transactions.get(reference)
        if tx is None:
            return VerifiedTransaction(reference, "abandoned", 0, "NGN", None)
        status: TxStatus = "failed" if "fail" in tx["email"].lower() else "success"
        return VerifiedTransaction(
            reference=reference,
            status=status,
            amount_kobo=tx["amount"],
            currency="NGN",
            paid_at=datetime.now().astimezone() if status == "success" else None,
            raw={"fake": True, **tx},
        )


_fake = FakeGateway()


def get_gateway() -> PaymentGateway:
    if settings.payment_provider == "paystack":
        return PaystackGateway(settings.paystack_secret_key, settings.paystack_base_url)
    return _fake
