import pytest
from httpx import AsyncClient
from redis.asyncio import Redis

from tests.api.helpers import auth_headers, register_and_verify

pytestmark = pytest.mark.api


async def test_project_crud_round_trip(client: AsyncClient, redis_client: Redis):
    await register_and_verify(client, redis_client, "owner@example.com")
    headers = await auth_headers(client, "owner@example.com")

    created = await client.post(
        "/api/v1/projects", json={"name": "Roadmap", "description": "Q3"}, headers=headers
    )
    assert created.status_code == 201
    project_id = created.json()["id"]

    listed = await client.get("/api/v1/projects", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    fetched = await client.get(f"/api/v1/projects/{project_id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Roadmap"

    updated = await client.patch(
        f"/api/v1/projects/{project_id}", json={"description": "Q4"}, headers=headers
    )
    assert updated.status_code == 200
    assert updated.json()["description"] == "Q4"
    assert updated.json()["name"] == "Roadmap"  # untouched

    deleted = await client.delete(f"/api/v1/projects/{project_id}", headers=headers)
    assert deleted.status_code == 204

    gone = await client.get(f"/api/v1/projects/{project_id}", headers=headers)
    assert gone.status_code == 404


async def test_project_not_owned_returns_404_not_403(client: AsyncClient, redis_client: Redis):
    await register_and_verify(client, redis_client, "alice@example.com")
    await register_and_verify(client, redis_client, "eve@example.com")
    alice_headers = await auth_headers(client, "alice@example.com")
    eve_headers = await auth_headers(client, "eve@example.com")

    created = await client.post(
        "/api/v1/projects", json={"name": "Alice's plan"}, headers=alice_headers
    )
    project_id = created.json()["id"]

    response = await client.get(f"/api/v1/projects/{project_id}", headers=eve_headers)

    assert response.status_code == 404


async def test_projects_require_authentication(client: AsyncClient):
    response = await client.get("/api/v1/projects")
    assert response.status_code in (401, 403)
