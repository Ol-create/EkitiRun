"""GPS housekeeping jobs. Owner: Lead (E13)."""

import logging
from typing import Any

from app.core.database import SessionLocal
from app.modules.gps.ingest import delete_old_positions

log = logging.getLogger("ekitirun.worker")


async def delete_old_gps_positions(ctx: dict[str, Any]) -> int:
    """Runners were promised their location history is deleted 30 days after the race."""
    async with SessionLocal() as session:
        deleted = await delete_old_positions(session, days=30)
    if deleted:
        log.info("Deleted %d GPS positions older than 30 days", deleted)
    return deleted
