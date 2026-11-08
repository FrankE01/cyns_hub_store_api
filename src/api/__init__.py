from fastapi import APIRouter

from api.core.config import settings
from api.schemas.health import Health, health

router: APIRouter = APIRouter(tags=["Health"], prefix=settings.api_v1_prefix)


@router.get("/")
async def get_health() -> Health:
    return health
