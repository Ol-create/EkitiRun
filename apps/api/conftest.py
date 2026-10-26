"""Shared test fixtures for tests/ and app/modules/*/tests/. Owner: Lead.

- `client`: an async HTTP client for the app. Use it for every API test.
- `redis` and `sms` (automatic in every test): an in-memory Redis and a fake SMS
  sender. Use `sms.last_code_for(phone)` to read an OTP that was "sent".
- `queued` (automatic): background jobs are recorded, not run: `[("render_receipt", [id])]`.
- `session`: a database session for tests that need Postgres. Each test runs
  inside a transaction that is rolled back afterwards, so tests never see each
  other's data. Requesting `session` (or `db_client`) makes the app use it too.

Database tests need Postgres. Locally, start it with `docker compose up -d db` (host port 5433).
They use a separate database, `ekitirun_test`, created automatically.
If Postgres isn't reachable, database tests are skipped (CI always has it).
"""

import os
import re
from collections.abc import AsyncIterator, Iterator

import pytest
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.core.database import get_session
from app.core.redis import get_redis
from app.core.sms import get_sms_sender
from app.main import app
from app.models import Base
from app.modules.timing import service as timing
from app.workers import queue

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://ekitirun:ekitirun@localhost:5433/ekitirun_test",
)


class FakeSms:
    """Records texts instead of sending them. `sms.last_code_for(phone)` reads the OTP back."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send(self, phone: str, message: str) -> None:
        self.sent.append((phone, message))

    def last_code_for(self, phone: str) -> str:
        message = next(m for p, m in reversed(self.sent) if p == phone)
        return re.search(r"\b(\d{6})\b", message).group(1)  # type: ignore[union-attr]


@pytest.fixture(autouse=True)
async def redis() -> AsyncIterator[FakeRedis]:
    """Every test gets an empty in-memory Redis; the real one is never touched."""
    fake = FakeRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_redis, None)
    await fake.aclose()


@pytest.fixture(autouse=True)
def sms() -> Iterator[FakeSms]:
    """Every test gets a fake SMS sender; nothing is ever really sent."""
    fake = FakeSms()
    app.dependency_overrides[get_sms_sender] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_sms_sender, None)


@pytest.fixture(autouse=True)
def instant_standings(monkeypatch) -> None:
    """Tests expect "mark changed, then read" to show the change at once; production
    rebuilds at most every 3 s (tested on its own in the timing tests)."""
    monkeypatch.setattr(timing, "MIN_REBUILD_S", 0)


@pytest.fixture(autouse=True)
def queued(monkeypatch) -> list[tuple[str, list[str]]]:
    """Every test records background jobs instead of queuing them: [(job, args), ...]."""
    jobs: list[tuple[str, list[str]]] = []

    async def record(job: str, job_args: list[str], job_id: str) -> None:
        jobs.append((job, job_args))

    monkeypatch.setattr(queue, "_push", record)
    return jobs


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
