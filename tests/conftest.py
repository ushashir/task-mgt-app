"""Fixtures for the integration and API tiers (Section 16).

Unit tests don't use anything here -- they construct fakes directly
(tests/unit/fakes.py) with no DB or Redis involved.

`DATABASE_URL`/`REDIS_URL` are read the same way the app reads them (via
Settings, Section 14) -- nothing is redirected behind the test's back. It's
the caller's responsibility to point those at disposable instances before
running `pytest -m integration` or `-m api` (see README/CONTRIBUTING): a
`taskdb_test` database and Redis db index 1 are the documented convention,
and CI wires up fresh service containers per Section 17.
"""

from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.db import get_db
from app.core.redis import get_redis
from app.main import app

settings = get_settings()
# NullPool: pytest-asyncio gives each test function its own event loop by
# default, but a pooled asyncpg connection is bound to the loop it was
# created on -- reusing one across tests corrupts it ("another operation is
# in progress"). NullPool opens a fresh connection per checkout instead of
# caching one in a pool, which sidesteps that entirely.
_test_engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """One connection + one outer transaction per test, rolled back at the
    end -- so nothing a test writes is ever actually committed, regardless
    of how many `session.flush()` calls happen along the way."""
    async with _test_engine.connect() as connection:
        outer_transaction = await connection.begin()
        session = AsyncSession(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session
        finally:
            await session.close()
            await outer_transaction.rollback()


@pytest_asyncio.fixture
async def redis_client() -> AsyncGenerator[Redis, None]:
    client: Redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    await client.flushdb()
    try:
        yield client
    finally:
        await client.flushdb()
        await client.aclose()


@pytest_asyncio.fixture
async def client(
    db_session: AsyncSession, redis_client: Redis
) -> AsyncGenerator[AsyncClient, None]:
    """An httpx client wired to the app in-process, with get_db/get_redis
    overridden to the transactional/flushed fixtures above so every request
    in a test shares the same rollback-able state."""

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    async def _override_get_redis() -> AsyncGenerator[Redis, None]:
        yield redis_client

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_redis] = _override_get_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
