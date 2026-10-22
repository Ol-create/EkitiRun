"""PDF jobs. Owner: Lead (E6). Templates live in app/templates/pdf (Backend, B4)."""

import logging
import uuid
from typing import Any

from app.core.database import SessionLocal
from app.documents.pledges import DocumentNotReady, generate, pledges_missing_documents

log = logging.getLogger("ekitirun.worker")


async def render_invoice(ctx: dict[str, Any], pledge_id: str) -> str | None:
    async with SessionLocal() as session:
        return await generate(session, uuid.UUID(pledge_id), "invoice")


async def render_receipt(ctx: dict[str, Any], pledge_id: str) -> str | None:
    async with SessionLocal() as session:
        try:
            return await generate(session, uuid.UUID(pledge_id), "receipt")
        except DocumentNotReady as exc:
            log.warning("Receipt skipped: %s", exc)
            return None


async def render_missing_documents(ctx: dict[str, Any]) -> int:
    """Repair job: make any invoice or receipt that was missed (e.g. Redis was down)."""
    async with SessionLocal() as session:
        missing = await pledges_missing_documents(session)
    made = 0
    for pledge_id, kind in missing:
        try:
            async with SessionLocal() as session:
                if await generate(session, pledge_id, kind):
                    made += 1
        except Exception:
            log.exception("Couldn't render %s for pledge %s", kind, pledge_id)
    if made:
        log.info("Repair job rendered %d missing document(s)", made)
    return made
