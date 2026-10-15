"""Files the stubs link to. Not part of the API contract; mounted outside production only."""

from typing import Literal

from fastapi import APIRouter, Response

from app.stubs.pdf import simple_pdf

router = APIRouter(prefix="/stub-files", include_in_schema=False)


@router.get("/{kind}/{reference}.pdf")
async def stub_pdf(kind: Literal["invoice", "receipt"], reference: str) -> Response:
    title = "INVOICE" if kind == "invoice" else "RECEIPT - PAID"
    pdf = simple_pdf(
        [
            f"EkitiRun - Sponsor {title}",
            f"Reference: {reference}",
            "",
            "This is a placeholder PDF from the Phase 0 stub API.",
            "The real document comes from the PDF pipeline (E6, B4).",
        ]
    )
    return Response(pdf, media_type="application/pdf")
