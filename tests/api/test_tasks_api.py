import pytest
from httpx import AsyncClient
from redis.asyncio import Redis

from tests.api.helpers import auth_headers, register_and_verify

pytestmark = pytest.mark.api


async def _create_project(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post("/api/v1/projects", json={"name": "Backlog"}, headers=headers)
    project_id: str = response.json()["id"]
    return project_id


async def test_task_crud_round_trip(client: AsyncClient, redis_client: Redis):
    await register_and_verify(client, redis_client, "owner@example.com")
    headers = await auth_headers(client, "owner@example.com")
    project_id = await _create_project(client, headers)

    created = await client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Write tests", "priority": "high"},
        headers=headers,
    )
    assert created.status_code == 201
    task_id = created.json()["id"]
    assert created.json()["status"] == "todo"  # default

    updated = await client.patch(
        f"/api/v1/tasks/{task_id}", json={"status": "in_progress"}, headers=headers
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "in_progress"

    deleted = await client.delete(f"/api/v1/tasks/{task_id}", headers=headers)
    assert deleted.status_code == 204

    gone = await client.get(f"/api/v1/tasks/{task_id}", headers=headers)
    assert gone.status_code == 404


async def test_task_pagination_and_filtering(client: AsyncClient, redis_client: Redis):
    await register_and_verify(client, redis_client, "owner@example.com")
    headers = await auth_headers(client, "owner@example.com")
    project_id = await _create_project(client, headers)

    for i in range(3):
        await client.post(
            "/api/v1/tasks",
            json={"project_id": project_id, "title": f"Task {i}", "priority": "low"},
            headers=headers,
        )
    await client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Urgent fix", "priority": "high"},
        headers=headers,
    )

    page1 = await client.get("/api/v1/tasks?page=1&page_size=2", headers=headers)
    assert page1.status_code == 200
    assert page1.json()["total"] == 4
    assert len(page1.json()["items"]) == 2

    page2 = await client.get("/api/v1/tasks?page=2&page_size=2", headers=headers)
    assert len(page2.json()["items"]) == 2

    high_priority = await client.get("/api/v1/tasks?priority=high", headers=headers)
    assert high_priority.json()["total"] == 1
    assert high_priority.json()["items"][0]["title"] == "Urgent fix"

    search = await client.get("/api/v1/tasks?search=Urgent", headers=headers)
    assert search.json()["total"] == 1


async def test_create_task_in_unowned_project_returns_404(client: AsyncClient, redis_client: Redis):
    await register_and_verify(client, redis_client, "alice@example.com")
    await register_and_verify(client, redis_client, "eve@example.com")
    alice_headers = await auth_headers(client, "alice@example.com")
    eve_headers = await auth_headers(client, "eve@example.com")
    project_id = await _create_project(client, alice_headers)

    response = await client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Sneaky task"},
        headers=eve_headers,
    )

    assert response.status_code == 404


async def test_deleting_project_cascades_to_its_tasks(client: AsyncClient, redis_client: Redis):
    await register_and_verify(client, redis_client, "owner@example.com")
    headers = await auth_headers(client, "owner@example.com")
    project_id = await _create_project(client, headers)
    created = await client.post(
        "/api/v1/tasks", json={"project_id": project_id, "title": "Doomed"}, headers=headers
    )
    task_id = created.json()["id"]

    await client.delete(f"/api/v1/projects/{project_id}", headers=headers)

    response = await client.get(f"/api/v1/tasks/{task_id}", headers=headers)
    assert response.status_code == 404
