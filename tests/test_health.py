import pytest
from httpx import AsyncClient

from api import get_health
from api.core.config import settings
from api.schemas.health import Health


@pytest.mark.asyncio
async def test_health_unit() -> None:
    """Direct unit test of the health endpoint handler."""
    res = await get_health()
    assert isinstance(res, Health)
    assert res.status == "ok"
    assert res.version == settings.version


@pytest.mark.asyncio
async def test_health_endpoint(async_client: AsyncClient) -> None:
    """Integration test verifying GET /api/v1/ returns 200 OK and valid health payload."""
    response = await async_client.get(f"{settings.api_v1_prefix}/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == settings.version
