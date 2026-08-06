"""Shared helpers for the API tier -- registers and verifies a user the way
a real client would (through the API), grabbing the verification token from
Redis directly since there's no real inbox to check in a test."""

from httpx import AsyncClient
from redis.asyncio import Redis

DEFAULT_PASSWORD = "Str0ng!Pass1"


async def register_and_verify(
    client: AsyncClient,
    redis_client: Redis,
    email: str,
    password: str = DEFAULT_PASSWORD,
    full_name: str = "Test User",
) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": full_name},
    )
    assert response.status_code == 201, response.text

    keys = await redis_client.keys("email_verify:*")
    token = None
    for key in keys:
        if await redis_client.get(key) == response.json()["id"]:
            token = key.split(":", 1)[1]
            break
    assert token is not None, "verification token was not stored in Redis"

    verify_response = await client.post("/api/v1/auth/verify-email", json={"token": token})
    assert verify_response.status_code == 200, verify_response.text


async def auth_headers(
    client: AsyncClient, email: str, password: str = DEFAULT_PASSWORD
) -> dict[str, str]:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
