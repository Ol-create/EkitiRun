"""ARQ worker settings. Owner: Lead (E6).

Run with `arq app.workers.settings.WorkerSettings` (the `worker` service in docker-compose.yml).
"""

from typing import Any, ClassVar

from arq import cron
from arq.connections import RedisSettings

from app.core.config import settings
from app.workers.pdf import render_invoice, render_missing_documents, render_receipt


class WorkerSettings:
    functions: ClassVar[list[Any]] = [render_invoice, render_receipt]
    cron_jobs: ClassVar[list[Any]] = [
        cron(render_missing_documents, minute=set(range(0, 60, 5)), run_at_startup=True),
    ]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_tries = 3
    job_timeout = 120
