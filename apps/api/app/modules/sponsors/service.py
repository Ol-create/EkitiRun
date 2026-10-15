"""Database and business logic for sponsors. Routers call this; it never imports FastAPI.

STUB(B1, B2): fake tiers and pledges, nothing is saved. Stub rules:
- The Paystack step is skipped: `authorization_url` goes straight to the thank-you page.
- A pledge whose company name contains "fail" ends up `failed`; one containing
  "pending" stays `pending`; any other pledge is `paid`.
"""

import secrets

from app.core.config import settings
from app.core.errors import AppError
from app.modules.sponsors.schemas import (
    PledgeCreated,
    PledgeIn,
    PledgeStatusOut,
    SponsorTierIn,
    SponsorTierOut,
    SponsorTierPatch,
)

_TIERS = [
    SponsorTierOut(id=1, name="Platinum", amount_kobo=500_000_000, sort_order=1,
                   benefits=["Logo on bibs and finish arch", "Naming of the Full Marathon",
                             "10 VIP passes", "Stand at the race expo"]),
    SponsorTierOut(id=2, name="Gold", amount_kobo=200_000_000, sort_order=2,
                   benefits=["Logo on finisher medals", "5 VIP passes", "Stand at the race expo"]),
    SponsorTierOut(id=3, name="Silver", amount_kobo=50_000_000, sort_order=3,
                   benefits=["Logo on the sponsor wall", "2 VIP passes"]),
]  # fmt: skip


def _tier(tier_id: int) -> SponsorTierOut:
    tier = next((t for t in _TIERS if t.id == tier_id), None)
    if tier is None:
        raise AppError(404, "TIER_NOT_FOUND", "That sponsorship tier does not exist.")
    return tier


async def list_tiers() -> list[SponsorTierOut]:
    return sorted(_TIERS, key=lambda t: t.sort_order)


async def create_tier(body: SponsorTierIn) -> SponsorTierOut:
    return SponsorTierOut(id=max(t.id for t in _TIERS) + 1, **body.model_dump())


async def update_tier(tier_id: int, body: SponsorTierPatch) -> SponsorTierOut:
    return _tier(tier_id).model_copy(update=body.model_dump(exclude_unset=True))


async def delete_tier(tier_id: int) -> None:
    _tier(tier_id)


def _pdf_url(kind: str, reference: str) -> str:
    return f"{settings.public_api_url}/api/v1/stub-files/{kind}/{reference}.pdf"


async def create_pledge(body: PledgeIn) -> PledgeCreated:
    if body.tier_id is not None:
        _tier(body.tier_id)
    name = body.company_name.lower()
    suffix = "-FAIL" if "fail" in name else "-PEND" if "pending" in name else ""
    reference = f"EKR-{secrets.token_hex(5).upper()}{suffix}"
    return PledgeCreated(
        reference=reference,
        authorization_url=f"{settings.public_web_url}/sponsors/thank-you?reference={reference}",
        invoice_pdf_url=_pdf_url("invoice", reference),
    )


async def get_pledge(reference: str) -> PledgeStatusOut:
    if not reference.startswith("EKR-"):
        raise AppError(404, "PLEDGE_NOT_FOUND", "No pledge with that reference.")
    status = (
        "failed"
        if reference.endswith("-FAIL")
        else "pending"
        if reference.endswith("-PEND")
        else "paid"
    )
    return PledgeStatusOut(
        reference=reference,
        company_name="Stub Sponsor Ltd",
        amount_kobo=_TIERS[1].amount_kobo,
        status=status,  # type: ignore[arg-type]
        receipt_pdf_url=_pdf_url("receipt", reference) if status == "paid" else None,
    )
