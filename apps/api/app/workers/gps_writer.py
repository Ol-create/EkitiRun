"""GPS writer: moves positions from the Redis stream into Postgres. Owner: Lead (E13).

Run it as its own process (the `gps-writer` service in docker-compose.yml):

    python -m app.workers.gps_writer

It reads up to 2,000 points at a time from the "gps:positions" stream (consumer
group "gps-writers"), saves them in bulk and only then acknowledges them. Several
writers can run side by side: Redis shares the stream out between them. Points a
crashed writer had read but not saved are reclaimed after a minute.
"""

import asyncio
import logging
import os
import socket

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from app.core.config import settings
from app.core.database import SessionLocal
from app.modules.gps.ingest import (
    GROUP,
    STREAM,
    TrackerIndex,
    decode_entries,
    write_batch,
)
from app.modules.gps.live import update_live

log = logging.getLogger("ekitirun.gps_writer")
BATCH = 2_000
BLOCK_MS = 1_000
RECLAIM_IDLE_MS = 60_000


async def ensure_group(redis: Redis) -> None:
    try:
        await redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def process_once(redis: Redis, trackers: TrackerIndex, consumer: str) -> int:
    """Read one batch (or reclaim a stalled one), save it, acknowledge it. Returns its size."""
    _, claimed, *_ = await redis.xautoclaim(
        STREAM, GROUP, consumer, min_idle_time=RECLAIM_IDLE_MS, count=BATCH
    )
    entries = claimed
    if not entries:
        response = await redis.xreadgroup(
            GROUP, consumer, {STREAM: ">"}, count=BATCH, block=BLOCK_MS
        )
        entries = response[0][1] if response else []
    if not entries:
        return 0
    positions = decode_entries(entries)
    async with SessionLocal() as session:
        stats = await write_batch(session, trackers, positions)
    await redis.xack(STREAM, GROUP, *[entry_id for entry_id, _ in entries])
    try:
        await update_live(redis, trackers, positions)  # the maps (E14); saved either way
    except Exception:
        log.exception("Live position update failed for a saved batch")
    if stats.ignored or stats.off_route:
        log.info(
            "GPS batch: %d saved (%d off route), %d from unassigned trackers ignored",
            stats.saved, stats.off_route, stats.ignored,
        )  # fmt: skip
    return len(entries)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    consumer = f"{socket.gethostname()}-{os.getpid()}"
    trackers = TrackerIndex()
    await ensure_group(redis)
    log.info("GPS writer %s reading %s", consumer, STREAM)
    while True:
        try:
            await process_once(redis, trackers, consumer)
        except Exception:
            log.exception("GPS batch failed; it stays in the stream and is retried")
            await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
