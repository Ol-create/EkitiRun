"""payments endpoints. Owner: Lead (E5).

This webhook is the ONLY public way a pledge becomes `paid`.
"""

from typing import Annotated

from fastapi import APIRouter, Header, Request

from app.core.deps import SessionDep
from app.core.schemas import error_responses
from app.modules.payments import service

router = APIRouter(prefix="/webhooks", tags=["payments"])


@router.post("/paystack", responses=error_responses(400, 401, 502))
async def paystack_webhook(
    request: Request,
    session: SessionDep,
    x_paystack_signature: Annotated[str | None, Header()] = None,
) -> dict[str, bool]:
    """Paystack calls this after a payment. Set its URL in the Paystack dashboard:
    Settings > API Keys & Webhooks > `https://<api host>/api/v1/webhooks/paystack`.
    """
    # The signature covers the exact bytes Paystack sent, so read the raw body.
    await service.handle_webhook(session, await request.body(), x_paystack_signature)
    return {"received": True}
