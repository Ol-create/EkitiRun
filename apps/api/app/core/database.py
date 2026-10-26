from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings


def engine_options(url: str) -> dict[str, Any]:
    """Connection settings for the database at `url`.

    Behind a transaction pooler (PgBouncer, e.g. Neon's "-pooler" host), asyncpg's
    prepared-statement cache breaks with "prepared statement does not exist" errors
    under load, so it is turned off there.
    """
    options: dict[str, Any] = {
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_pre_ping": True,  # survive the database dropping idle connections
        "pool_recycle": 1800,
    }
    if "-pooler" in url or "pgbouncer=true" in url:
        options["connect_args"] = {"statement_cache_size": 0, "prepared_statement_cache_size": 0}
    return options


engine = create_async_engine(settings.database_url, **engine_options(settings.database_url))
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
