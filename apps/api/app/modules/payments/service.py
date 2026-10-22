"""Sponsor payments through Paystack. Owner: Lead (E5).

For Backend (B2), the whole interface is:

    pledge = Pledge(..., reference=payments.new_reference(), status="pending")
    checkout = await payments.start_checkout(pledge, sponsor.email)
    # return checkout.reference and checkout.authorization_url

    # optional, in GET /sponsors/pledges/{reference}, before reading the status:
    await payments.sync_pledge(session, reference)

Only this module ever sets a pledge to `paid` or `failed`.

Pledge states: pending -> paid, pending -> failed, failed -> paid (a later
attempt succeeded). `paid` is final. Every settlement re-verifies the
transaction with Paystack (the webhook body alone is never trusted), checks
the amount and currency, and runs under a row lock, so a webhook delivered
twice, or a webhook racing a status check, settles the pledge exactly once.
"""

import json
import logging
import secrets
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import Payment, Pledge
from app.modules.payments.gateway import (
    Checkout,
    GatewayError,
    PaymentGateway,
    get_gateway,
    signature_is_valid,
)
from app.workers.queue import enqueue

log = logging.getLogger("ekitirun.payments")


def new_reference() -> str:
    """A unique pledge reference, also used as the Paystack transaction reference."""
    return f"EKR-{secrets.token_hex(6).upper()}"


async def start_checkout(
    pledge: Pledge, email: str, gateway: PaymentGateway | None = None
) -> Checkout:
    """Create the Paystack checkout for a pending pledge. Raises 502 PAYMENT_PROVIDER_ERROR."""
    gateway = gateway or get_gateway()
    try:
        return await gateway.initialize(
            reference=pledge.reference,
            amount_kobo=pledge.amount_kobo,
            email=email,
            metadata={"pledge_id": str(pledge.id), "kind": "sponsorship"},
        )
    except GatewayError as exc:
        log.error("Paystack initialize failed for %s: %s", pledge.reference, exc)
        raise AppError(
            502, "PAYMENT_PROVIDER_ERROR", "We couldn't start the payment. Please try again."
        ) from None


async def settle(
    session: AsyncSession, reference: str, event: str, gateway: PaymentGateway | None = None
) -> Pledge | None:
    """Verify `reference` with Paystack and update its pledge. Commits.

    Returns the pledge, or None when no pledge has this reference.
    Raises GatewayError if Paystack can't be reached (the caller decides to retry).
    Paths that change nothing also commit (never roll back), which releases the
    row lock without discarding anything else the caller has in the session.
    """
    gateway = gateway or get_gateway()
    pledge = await session.scalar(
        select(Pledge).where(Pledge.reference == reference).with_for_update()
    )
    if pledge is None:
        await session.commit()
        return None
    if pledge.status == "paid":
        await session.commit()
        return pledge  # already settled: nothing to do

    try:
        tx = await gateway.verify(reference)
    except GatewayError:
        await session.commit()  # release the lock; the pledge is unchanged
        raise
    if tx.status == "pending" or tx.status == "abandoned":
        await session.commit()
        return pledge

    outcome: str = tx.status
    if tx.status == "success" and (tx.amount_kobo != pledge.amount_kobo or tx.currency != "NGN"):
        outcome = "amount_mismatch"
        log.error(
            "Pledge %s: paid %s %s but expected %s NGN. Not marking paid; check it by hand.",
            reference, tx.amount_kobo, tx.currency, pledge.amount_kobo,
        )  # fmt: skip

    await session.execute(
        insert(Payment)
        .values(
            pledge_id=pledge.id,
            provider="paystack",
            provider_reference=reference,
            event=event,
            amount_kobo=tx.amount_kobo,
            status=outcome,
            raw=json.loads(json.dumps(tx.raw, default=str)),
        )
        .on_conflict_do_nothing(constraint="uq_payments_provider_event")
    )
    if outcome == "success":
        pledge.status = "paid"
        pledge.paid_at = tx.paid_at or datetime.now(UTC)
    elif outcome == "failed" and pledge.status == "pending":
        pledge.status = "failed"
    await session.commit()
    if outcome == "success":
        await enqueue("render_receipt", pledge.id)  # after commit, so the worker sees `paid`
    return pledge


async def sync_pledge(
    session: AsyncSession, reference: str, gateway: PaymentGateway | None = None
) -> None:
    """Check a pending pledge with Paystack now, in case its webhook hasn't arrived yet.

    Never raises for provider problems: the webhook will settle it later.
    """
    status = await session.scalar(select(Pledge.status).where(Pledge.reference == reference))
    if status not in ("pending", "failed"):
        return
    try:
        await settle(session, reference, event="verify", gateway=gateway)
    except GatewayError as exc:
        log.warning("Couldn't check pledge %s with Paystack: %s", reference, exc)


async def handle_webhook(
    session: AsyncSession,
    raw_body: bytes,
    signature: str | None,
    gateway: PaymentGateway | None = None,
) -> str:
    """Process one Paystack webhook. Returns what happened, for logs and tests.

    Raises 401 for a bad signature, and 502 if Paystack can't be reached to verify
    (Paystack then retries the webhook later).
    """
    if not signature_is_valid(raw_body, signature):
        raise AppError(401, "INVALID_SIGNATURE", "Webhook signature is not valid.")
    try:
        payload: dict[str, Any] = json.loads(raw_body)
    except ValueError:
        raise AppError(400, "INVALID_PAYLOAD", "Webhook body is not JSON.") from None

    event = str(payload.get("event", ""))
    reference = str((payload.get("data") or {}).get("reference") or "")
    if event not in ("charge.success", "charge.failed") or not reference:
        return "ignored"
    try:
        pledge = await settle(session, reference, event=event, gateway=gateway)
    except GatewayError as exc:
        log.error("Webhook for %s: couldn't verify with Paystack: %s", reference, exc)
        raise AppError(
            502, "PAYMENT_PROVIDER_ERROR", "Couldn't verify with Paystack; retry later."
        ) from None
    if pledge is None:
        log.warning("Webhook for unknown reference %s ignored", reference)
        return "unknown_reference"
    return pledge.status
