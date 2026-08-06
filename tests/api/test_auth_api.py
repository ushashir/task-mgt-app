"""Full request/response cycle over the ASGI app (Section 16 API tier).
Business-rule edge cases are already covered at the unit/integration tiers;
this tier asserts the HTTP contract -- status codes and response shape --
end to end, plus the lockout scenario reproduced against the real stack one
level up from test_redis_lockout.py."""

import pytest
from httpx import AsyncClient
from redis.asyncio import Redis

from tests.api.helpers import DEFAULT_PASSWORD, auth_headers, register_and_verify

pytestmark = pytest.mark.api


async def test_register_returns_201_with_user_body(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "new@example.com", "password": DEFAULT_PASSWORD, "full_name": "New User"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@example.com"
    assert body["is_email_verified"] is True
    assert "password" not in body
    assert "password_hash" not in body


async def test_register_duplicate_email_returns_409(client: AsyncClient, redis_client: Redis):
    await register_and_verify(client, redis_client, "dupe@example.com")

    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "dupe@example.com", "password": DEFAULT_PASSWORD, "full_name": "Again"},
    )

    assert response.status_code == 409


async def test_register_weak_password_returns_422(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "weak@example.com", "password": "weakpassword", "full_name": "Weak"},
    )

    assert response.status_code == 422


async def test_verify_email_token_is_single_use(client: AsyncClient, redis_client: Redis):
    await register_and_verify(client, redis_client, "single@example.com")
    keys = await redis_client.keys("email_verify:*")
    assert keys == []  # deleted on first use

    replay = await client.post("/api/v1/auth/verify-email", json={"token": "whatever-was-there"})
    assert replay.status_code == 400


async def test_login_succeeds_without_explicit_verification(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "onboarded@example.com", "password": DEFAULT_PASSWORD, "full_name": "U"},
    )

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "onboarded@example.com", "password": DEFAULT_PASSWORD},
    )

    assert response.status_code == 200


async def test_login_wrong_password_returns_401(client: AsyncClient, redis_client: Redis):
    await register_and_verify(client, redis_client, "correct@example.com")

    response = await client.post(
        "/api/v1/auth/login", json={"email": "correct@example.com", "password": "WrongPass1!"}
    )

    assert response.status_code == 401


async def test_login_locks_out_after_threshold_and_returns_423(
    client: AsyncClient, redis_client: Redis
):
    await register_and_verify(client, redis_client, "locktarget@example.com")

    for _ in range(5):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "locktarget@example.com", "password": "WrongPass1!"},
        )
        assert resp.status_code == 401

    locked = await client.post(
        "/api/v1/auth/login",
        json={"email": "locktarget@example.com", "password": DEFAULT_PASSWORD},
    )
    assert locked.status_code == 423
    assert "Retry-After" in locked.headers


async def test_full_login_flow_and_me_endpoint(client: AsyncClient, redis_client: Redis):
    await register_and_verify(client, redis_client, "full@example.com")
    headers = await auth_headers(client, "full@example.com")

    me = await client.get("/api/v1/auth/me", headers=headers)

    assert me.status_code == 200
    assert me.json()["email"] == "full@example.com"


async def test_unauthenticated_request_is_rejected(client: AsyncClient):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code in (401, 403)


async def test_refresh_rotates_token_and_rejects_reuse(client: AsyncClient, redis_client: Redis):
    await register_and_verify(client, redis_client, "refresh@example.com")
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "refresh@example.com", "password": DEFAULT_PASSWORD},
    )
    old_refresh = login.json()["refresh_token"]

    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert refreshed.status_code == 200
    assert refreshed.json()["refresh_token"] != old_refresh

    reused = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert reused.status_code == 400


async def test_logout_returns_204(client: AsyncClient, redis_client: Redis):
    await register_and_verify(client, redis_client, "logout@example.com")
    login = await client.post(
        "/api/v1/auth/login", json={"email": "logout@example.com", "password": DEFAULT_PASSWORD}
    )

    response = await client.post(
        "/api/v1/auth/logout", json={"refresh_token": login.json()["refresh_token"]}
    )

    assert response.status_code == 204


async def test_forgot_password_response_is_identical_for_real_and_unknown_email(
    client: AsyncClient, redis_client: Redis
):
    await register_and_verify(client, redis_client, "known@example.com")

    real = await client.post("/api/v1/auth/forgot-password", json={"email": "known@example.com"})
    fake = await client.post("/api/v1/auth/forgot-password", json={"email": "unknown@example.com"})

    assert real.status_code == fake.status_code == 200
    assert real.json() == fake.json()


async def test_reset_password_flow_invalidates_old_password(
    client: AsyncClient, redis_client: Redis
):
    await register_and_verify(client, redis_client, "reset@example.com")
    await client.post("/api/v1/auth/forgot-password", json={"email": "reset@example.com"})

    keys = await redis_client.keys("pwd_reset:*")
    assert len(keys) == 1
    token = keys[0].split(":", 1)[1]

    reset = await client.post(
        "/api/v1/auth/reset-password", json={"token": token, "new_password": "New1!Pass99"}
    )
    assert reset.status_code == 200

    old_login = await client.post(
        "/api/v1/auth/login", json={"email": "reset@example.com", "password": DEFAULT_PASSWORD}
    )
    assert old_login.status_code == 401

    new_login = await client.post(
        "/api/v1/auth/login", json={"email": "reset@example.com", "password": "New1!Pass99"}
    )
    assert new_login.status_code == 200
