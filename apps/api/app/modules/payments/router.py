"""payments endpoints. Owner: Lead (E5).

This webhook is the ONLY place a pledge may become `paid`.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/webhooks", tags=["payments"])


@router.post("/paystack")
async def paystack_webhook() -> dict[str, bool]:
    # STUB(E5): verify x-paystack-signature, re-verify with Paystack, record the
    # Payment once per event, then mark the pledge paid or failed.
    return {"received": True}
