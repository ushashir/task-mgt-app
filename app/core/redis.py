"""Async Redis client, used for auth tokens and login lockout state (Section 7)."""

from collections.abc import AsyncGenerator

from redis.asyncio import Redis

from app.core.config import get_settings

settings = get_settings()

_redis_pool: Redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)


async def get_redis() -> AsyncGenerator[Redis, None]:
    yield _redis_pool


async def close_redis() -> None:
    await _redis_pool.aclose()
