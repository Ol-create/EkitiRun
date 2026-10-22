"""Sponsor invoices and receipts. Owner: Lead (E6).

`document_context()` is everything a template can use. Backend (B4) designs
app/templates/pdf/invoice.html and receipt.html around it; ask Lead for new fields.

    org.name, org.address, org.email
    org.bank_name, org.bank_account_name, org.bank_account_number   (invoice: pay by transfer)
    document.kind ("invoice" | "receipt"), document.number, document.issued_on,
    document.due_on (invoice)
    sponsor.company_name, sponsor.contact_name, sponsor.email, sponsor.phone
    pledge.reference, pledge.tier_name ("Custom" for a custom amount),
    pledge.amount_kobo (use the `naira` filter: {{ pledge.amount_kobo | naira }}),
    pledge.paid_at (receipt), pledge.payment_reference (receipt: the Paystack reference)
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.storage import private_key, save_file
from app.documents.render import render_pdf
from app.models import Payment, Pledge, Sponsor, SponsorTier

Kind = Literal["invoice", "receipt"]


def document_number(kind: Kind, reference: str) -> str:
    return f"{'INV' if kind == 'invoice' else 'RCT'}-{reference.removeprefix('EKR-')}"


def document_context(
    kind: Kind,
    pledge: Pledge,
    sponsor: Sponsor,
    tier: SponsorTier | None,
    payment_reference: str | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    issued_on = (pledge.paid_at.date() if kind == "receipt" and pledge.paid_at else None) or (
        today or datetime.now(UTC).date()
    )
    return {
        "org": {
            "name": settings.organiser_name,
            "address": settings.organiser_address,
            "email": settings.organiser_email,
            "bank_name": settings.bank_name,
            "bank_account_name": settings.bank_account_name,
            "bank_account_number": settings.bank_account_number,
        },
        "document": {
            "kind": kind,
            "number": document_number(kind, pledge.reference),
            "issued_on": issued_on,
            "due_on": issued_on + timedelta(days=settings.invoice_due_days)
            if kind == "invoice"
            else None,
        },
        "sponsor": {
            "company_name": sponsor.company_name,
            "contact_name": sponsor.contact_name,
            "email": sponsor.email,
            "phone": sponsor.phone,
        },
        "pledge": {
            "reference": pledge.reference,
            "tier_name": tier.name if tier else "Custom",
            "amount_kobo": pledge.amount_kobo,
            "paid_at": pledge.paid_at,
            "payment_reference": payment_reference,
        },
    }


class DocumentNotReady(Exception):
    """A receipt was requested for a pledge that isn't paid."""


async def generate(session: AsyncSession, pledge_id: uuid.UUID, kind: Kind) -> str | None:
    """Render and store the pledge's invoice or receipt, and save its URL. Commits.

    Returns the URL. Does nothing (returns the existing URL) if it was already made,
    so running a job twice is harmless. Returns None for an unknown pledge.
    """
    pledge = await session.scalar(select(Pledge).where(Pledge.id == pledge_id).with_for_update())
    if pledge is None:
        await session.commit()
        return None
    existing = pledge.invoice_pdf_url if kind == "invoice" else pledge.receipt_pdf_url
    if existing:
        await session.commit()
        return existing
    if kind == "receipt" and pledge.status != "paid":
        await session.commit()
        raise DocumentNotReady(f"Pledge {pledge.reference} is {pledge.status}, not paid")

    sponsor = await session.get(Sponsor, pledge.sponsor_id)
    assert sponsor is not None
    tier = await session.get(SponsorTier, pledge.tier_id) if pledge.tier_id else None
    payment_reference = None
    if kind == "receipt":
        payment_reference = await session.scalar(
            select(Payment.provider_reference)
            .where(Payment.pledge_id == pledge.id, Payment.status == "success")
            .limit(1)
        )

    pdf = render_pdf(
        f"{kind}.html", document_context(kind, pledge, sponsor, tier, payment_reference)
    )
    key = private_key(f"pledges/{pledge.reference}", kind, "pdf")
    url = await save_file(session, key, pdf, "application/pdf")
    if kind == "invoice":
        pledge.invoice_pdf_url = url
    else:
        pledge.receipt_pdf_url = url
    await session.commit()
    return url


async def pledges_missing_documents(session: AsyncSession, limit: int = 50) -> list[tuple]:
    """(pledge_id, kind) pairs whose invoice or receipt hasn't been made yet."""
    missing_invoice = select(Pledge.id).where(Pledge.invoice_pdf_url.is_(None)).limit(limit)
    missing_receipt = (
        select(Pledge.id)
        .where(Pledge.status == "paid", Pledge.receipt_pdf_url.is_(None))
        .limit(limit)
    )
    return [(pid, "invoice") for pid in await session.scalars(missing_invoice)] + [
        (pid, "receipt") for pid in await session.scalars(missing_receipt)
    ]
