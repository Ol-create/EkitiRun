"""Sponsor invoices and receipts: rendering, storage, serving and queuing (E6)."""

import io
from datetime import UTC, datetime

import pytest
from pypdf import PdfReader
from sqlalchemy import func, select

from app.core.storage import load_file
from app.documents import pledges as documents
from app.documents.render import naira, render_html
from app.models import Payment, Pledge, Sponsor, SponsorTier, StoredFile
from app.workers import queue


def pdf_text(data: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(data)).pages)


async def make_pledge(session, *, status="pending", tier=True, company="Fountain Foods Ltd"):
    sponsor = Sponsor(
        company_name=company,
        contact_name="Funmilayo Adebayo",
        email="partnerships@fountainfoods.ng",
        phone="+2348031234567",
    )
    session.add(sponsor)
    gold = None
    if tier:
        gold = SponsorTier(name="Gold", amount_kobo=200_000_000, benefits=["Logo"], sort_order=2)
        session.add(gold)
    await session.flush()
    pledge = Pledge(
        sponsor_id=sponsor.id,
        tier_id=gold.id if gold else None,
        amount_kobo=200_000_000 if tier else 1_500_000,
        reference="EKR-1A2B3C4D5E6F",
        status=status,
        paid_at=datetime(2027, 1, 10, 9, 30, tzinfo=UTC) if status == "paid" else None,
    )
    session.add(pledge)
    await session.flush()
    return pledge


def test_naira_formatting():
    assert naira(200_000_000) == "₦2,000,000.00"
    assert naira(1_050) == "₦10.50"


async def test_invoice_is_rendered_stored_and_linked(session):
    pledge = await make_pledge(session)

    url = await documents.generate(session, pledge.id, "invoice")

    assert url == pledge.invoice_pdf_url
    key = url.split("/api/v1/files/", 1)[1]
    assert key.startswith("pledges/EKR-1A2B3C4D5E6F/invoice-")
    stored = await load_file(session, key)
    assert stored.content_type == "application/pdf"
    text = pdf_text(stored.data)
    for expected in ("INV-1A2B3C4D5E6F", "Fountain Foods Ltd", "Gold", "2,000,000.00", "Due"):
        assert expected in text


async def test_generating_twice_reuses_the_document(session):
    pledge = await make_pledge(session)

    first = await documents.generate(session, pledge.id, "invoice")
    second = await documents.generate(session, pledge.id, "invoice")

    assert first == second
    assert await session.scalar(select(func.count()).select_from(StoredFile)) == 1


async def test_receipt_needs_a_paid_pledge(session):
    pledge = await make_pledge(session)

    with pytest.raises(documents.DocumentNotReady):
        await documents.generate(session, pledge.id, "receipt")
    assert pledge.receipt_pdf_url is None


async def test_receipt_shows_paid_and_the_payment_reference(session):
    pledge = await make_pledge(session, status="paid")
    session.add(
        Payment(
            pledge_id=pledge.id,
            provider_reference=pledge.reference,
            event="charge.success",
            amount_kobo=pledge.amount_kobo,
            status="success",
            raw={},
        )
    )
    await session.flush()

    url = await documents.generate(session, pledge.id, "receipt")

    stored = await load_file(session, url.split("/api/v1/files/", 1)[1])
    text = pdf_text(stored.data)
    for expected in ("RCT-1A2B3C4D5E6F", "PAID", "10 January 2027", "EKR-1A2B3C4D5E6F"):
        assert expected in text


async def test_custom_amount_says_custom(session):
    pledge = await make_pledge(session, tier=False)

    url = await documents.generate(session, pledge.id, "invoice")

    stored = await load_file(session, url.split("/api/v1/files/", 1)[1])
    assert "Sponsorship: Custom" in pdf_text(stored.data)


async def test_sponsor_names_cannot_inject_html(session):
    pledge = await make_pledge(session, company="<b>Evil</b> & Co")
    sponsor = await session.get(Sponsor, pledge.sponsor_id)

    html = render_html("invoice.html", documents.document_context("invoice", pledge, sponsor, None))

    assert "&lt;b&gt;Evil&lt;/b&gt; &amp; Co" in html
    assert "<b>Evil</b>" not in html


async def test_unknown_pledge_is_ignored(session):
    import uuid

    assert await documents.generate(session, uuid.uuid4(), "invoice") is None


async def test_missing_documents_are_found_for_the_repair_job(session):
    pending = await make_pledge(session)
    pending_id = pending.id

    missing = await documents.pledges_missing_documents(session)
    assert (pending_id, "invoice") in missing

    await documents.generate(session, pending_id, "invoice")
    assert (pending_id, "invoice") not in await documents.pledges_missing_documents(session)


# ---------------------------------------------------------------- serving


async def test_files_are_served_by_their_private_link(db_client, session):
    pledge = await make_pledge(session)
    url = await documents.generate(session, pledge.id, "invoice")

    response = await db_client.get(url.removeprefix("http://localhost:8000"))

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"].startswith("private")
    assert response.content.startswith(b"%PDF")


async def test_unknown_file_is_404(db_client):
    response = await db_client.get("/api/v1/files/pledges/EKR-X/invoice-guess.pdf")

    assert response.status_code == 404
    assert response.json()["code"] == "FILE_NOT_FOUND"


# ---------------------------------------------------------------- queue


async def test_enqueue_uses_one_job_id_per_document(queued):
    assert await queue.enqueue("render_invoice", "abc") is True
    assert queued == [("render_invoice", ["abc"])]


async def test_enqueue_never_fails_the_caller(monkeypatch):
    async def redis_down(*args):
        raise ConnectionError("redis down")

    monkeypatch.setattr(queue, "_push", redis_down)

    assert await queue.enqueue("render_invoice", "abc") is False
