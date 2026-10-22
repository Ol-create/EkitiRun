"""Putting jobs on the background queue. Owner: Lead (E6).

    from app.workers.queue import enqueue
    await enqueue("render_invoice", pledge.id)

Jobs run in the `worker` container (ARQ). The same job with the same argument
is only queued once at a time. If Redis is down, the job is skipped with a log
line instead of failing the request: the worker's repair job (every 5 minutes)
picks up any document that was missed.
"""

import logging
from typing import Any

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings

from app.core.config import settings

log = logging.getLogger("ekitirun.queue")
_pool: ArqRedis | None = None


async def _get_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _pool


async def _push(job: str, job_args: list[str], job_id: str) -> None:
    """Hand the job to ARQ. Tests replace this with a recorder (see conftest.py)."""
    pool = await _get_pool()
    await pool.enqueue_job(job, *job_args, _job_id=job_id)


async def enqueue(job: str, *args: Any) -> bool:
    """Queue `job(*args)`. Returns False (and logs) if it couldn't be queued."""
    job_args = [str(a) for a in args]
    try:
        await _push(job, job_args, f"{job}:{':'.join(job_args)}")
    except Exception as exc:  # Redis down or misconfigured: never fail the caller
        log.error("Couldn't queue %s%s: %s", job, tuple(job_args), exc)
        return False
    return True
