from fastapi import APIRouter

from api.core.config import settings
from api.core.database import check_database_health
from api.schemas.health import Health

router: APIRouter = APIRouter(tags=["Health"], prefix=settings.api_v1_prefix)


@router.get("/")
async def get_health() -> Health:
    """Health check endpoint reporting API version and database connectivity."""
    db_ok = await check_database_health()
    return Health(
        status="ok",
        version=settings.version,
        database="connected" if db_ok else "disconnected",
    )
