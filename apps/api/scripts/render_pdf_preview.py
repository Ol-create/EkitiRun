"""Render the invoice and receipt templates with sample data. Owner: Lead (E6).

For Backend (B4) while designing the templates. From apps/api:

    python -m scripts.render_pdf_preview

writes pdf-preview/invoice.pdf, receipt.pdf and the matching .html files (open the
HTML in a browser for quick layout work; the PDF is the real result). No database
or Redis needed.
"""

import uuid
from datetime import UTC, date, datetime
from pathlib import Path

from app.documents.pledges import document_context
from app.documents.render import render_html, render_pdf
from app.models import Pledge, Sponsor, SponsorTier

OUT = Path("pdf-preview")


def sample() -> tuple[Pledge, Sponsor, SponsorTier]:
    sponsor = Sponsor(
        id=uuid.uuid4(),
        company_name="Fountain Foods & Beverages Ltd",
        contact_name="Funmilayo Adebayo",
        email="partnerships@fountainfoods.ng",
        phone="+2348031234567",
    )
    tier = SponsorTier(id=2, name="Gold", amount_kobo=200_000_000, benefits=[], sort_order=2)
    pledge = Pledge(
        id=uuid.uuid4(),
        sponsor_id=sponsor.id,
        tier_id=tier.id,
        amount_kobo=tier.amount_kobo,
        reference="EKR-1A2B3C4D5E6F",
        status="paid",
        paid_at=datetime(2027, 1, 10, 9, 30, tzinfo=UTC),
    )
    return pledge, sponsor, tier


def main() -> None:
    OUT.mkdir(exist_ok=True)
    pledge, sponsor, tier = sample()
    for kind in ("invoice", "receipt"):
        context = document_context(
            kind, pledge, sponsor, tier, payment_reference=pledge.reference,
            today=date(2027, 1, 3),
        )  # fmt: skip
        (OUT / f"{kind}.html").write_text(render_html(f"{kind}.html", context), encoding="utf-8")
        (OUT / f"{kind}.pdf").write_bytes(render_pdf(f"{kind}.html", context))
        print(f"wrote {OUT / kind}.pdf")


if __name__ == "__main__":
    main()
