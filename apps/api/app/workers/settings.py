"""ARQ worker settings. Owner: Lead (E6)."""

from typing import Any, ClassVar

from arq.connections import RedisSettings

from app.core.config import settings
from app.workers.pdf import render_invoice, render_receipt


class WorkerSettings:
    functions: ClassVar[list[Any]] = [render_invoice, render_receipt]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
