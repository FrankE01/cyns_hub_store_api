from fastapi import APIRouter

from api.routers.v1.auth import router as auth_router
from api.routers.v1.health import router as health_router

v1_router = APIRouter()
v1_router.include_router(health_router)
v1_router.include_router(auth_router, prefix="/api/v1")

__all__ = ["v1_router"]
