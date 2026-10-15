"""Shared test fixtures for tests/ and app/modules/*/tests/. Owner: Lead.

- `client`: an async HTTP client for the app. Use it for every API test.
- `session`: a database session for tests that need Postgres. Each test runs
  inside a transaction that is rolled back afterwards, so tests never see each
  other's data. Requesting `session` (or `db_client`) makes the app use it too.

Database tests need Postgres. Locally, start it with `docker compose up -d db` (host port 5433).
They use a separate database, `ekitirun_test`, created automatically.
If Postgres isn't reachable, database tests are skipped (CI always has it).
"""

import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.core.database import get_session
from app.main import app
from app.models import Base

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://ekitirun:ekitirun@localhost:5433/ekitirun_test",
)


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _ensure_database(url: str) -> None:
    """Create the test database if it doesn't exist yet."""
    parsed = make_url(url)
    admin = create_async_engine(parsed.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": parsed.database},
            )
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{parsed.database}"'))
    finally:
        await admin.dispose()


@pytest.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    try:
        await _ensure_database(TEST_DATABASE_URL)
    except (OSError, ConnectionError) as exc:
        pytest.skip(f"Postgres not reachable for tests ({exc}). Run: docker compose up -d db")
    eng = create_async_engine(TEST_DATABASE_URL)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with engine.connect() as conn:
        trans = await conn.begin()
        # Code under test may call commit(); it only releases a savepoint.
        sess = AsyncSession(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )

        async def override() -> AsyncIterator[AsyncSession]:
            yield sess

        app.dependency_overrides[get_session] = override
        try:
            yield sess
        finally:
            app.dependency_overrides.pop(get_session, None)
            await sess.close()
            await trans.rollback()


@pytest.fixture
async def db_client(session: AsyncSession, client: AsyncClient) -> AsyncClient:
    """`client` wired to the test transaction."""
    return client
