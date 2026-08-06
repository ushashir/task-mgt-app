import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.api


async def test_health_reports_database_and_redis_connectivity(client: AsyncClient):
    response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"] == {"database": True, "redis": True}
