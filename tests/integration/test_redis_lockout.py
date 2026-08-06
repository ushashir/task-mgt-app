"""Real Postgres + real Redis. Covers the explicit Section 16 scenario:
"login lockout triggers after the configured attempt count and clears after
the lockout window" -- the unit tier (test_auth_service.py) verifies the
same logic against a fake Redis with no real expiry; this tier proves the
same behavior against actual `EXPIRE`/`TTL` semantics."""

import asyncio

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.repository import UserRepository
from app.auth.service import AuthService
from app.common.exceptions import AccountLockedError, InvalidCredentialsError
from app.core.security import hash_password

pytestmark = pytest.mark.integration


async def _make_verified_user(session: AsyncSession, email: str) -> User:
    repo = UserRepository(session)
    return await repo.add(
        User(
            email=email,
            password_hash=hash_password("Correct1!"),
            full_name="Test User",
            is_email_verified=True,
        )
    )


async def test_lockout_triggers_at_threshold_against_real_redis(
    db_session: AsyncSession, redis_client: Redis
):
    await _make_verified_user(db_session, "brute@example.com")
    service = AuthService(UserRepository(db_session), redis_client)
    max_attempts = service._settings.LOGIN_MAX_ATTEMPTS

    for _ in range(max_attempts):
        with pytest.raises(InvalidCredentialsError):
            await service.login("brute@example.com", "Wrong1!")

    with pytest.raises(AccountLockedError):
        await service.login("brute@example.com", "Correct1!")

    ttl = await redis_client.ttl("login_lock:brute@example.com")
    assert ttl > 0


async def test_login_lock_clears_once_the_redis_ttl_actually_expires(
    db_session: AsyncSession, redis_client: Redis
):
    await _make_verified_user(db_session, "locked@example.com")
    service = AuthService(UserRepository(db_session), redis_client)

    # Set the lock directly with a short TTL rather than driving it through
    # five failed logins with the real (15-minute) configured TTL -- this
    # is still testing real Redis expiry, just on a timescale a test suite
    # can afford.
    await redis_client.set("login_lock:locked@example.com", "1", ex=1)

    with pytest.raises(AccountLockedError):
        await service.login("locked@example.com", "Correct1!")

    await asyncio.sleep(1.2)

    access_token, refresh_token = await service.login("locked@example.com", "Correct1!")
    assert access_token and refresh_token
