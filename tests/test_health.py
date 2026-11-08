from unittest.mock import patch

import pytest
from httpx import AsyncClient

from api.core.config import settings
from api.routers.v1.health import get_health
from api.schemas.health import Health


@pytest.mark.asyncio
async def test_health_unit() -> None:
    """Direct unit test of the health endpoint handler."""
    with patch("api.routers.v1.health.check_database_health", return_value=True):
        res = await get_health()
        assert isinstance(res, Health)
        assert res.status == "ok"
        assert res.version == settings.version
        assert res.database == "connected"


@pytest.mark.asyncio
async def test_health_endpoint(async_client: AsyncClient) -> None:
    """Integration test verifying GET /api/v1/ returns 200 OK and valid health payload."""
    with patch("api.routers.v1.health.check_database_health", return_value=True):
        response = await async_client.get(f"{settings.api_v1_prefix}/")
        assert response.status_code == 200
        assert "x-request-id" in response.headers
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] == settings.version
        assert data["database"] == "connected"


@pytest.mark.asyncio
async def test_custom_request_id(async_client: AsyncClient) -> None:
    """Verifies that an incoming X-Request-ID header is preserved in the response."""
    custom_id = "test-trace-id-123"
    with patch("api.routers.v1.health.check_database_health", return_value=True):
        response = await async_client.get(
            f"{settings.api_v1_prefix}/", headers={"x-request-id": custom_id}
        )
        assert response.status_code == 200
        assert response.headers.get("x-request-id") == custom_id


@pytest.mark.asyncio
async def test_root_redirects_to_docs_in_development(
    async_client: AsyncClient,
) -> None:
    """Verifies that root / redirects to /docs in development mode."""
    with patch.object(settings, "env", "development"):
        response = await async_client.get("/", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"] == "/docs"


@pytest.mark.asyncio
async def test_root_returns_json_in_production(
    async_client: AsyncClient,
) -> None:
    """Verifies that root / returns 200 OK JSON status in production mode."""
    with (
        patch.object(settings, "env", "production"),
        patch.object(settings, "debug", False),
    ):
        response = await async_client.get("/", follow_redirects=False)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "online"
        assert data["version"] == settings.version
        assert data["api_v1"] == settings.api_v1_prefix
