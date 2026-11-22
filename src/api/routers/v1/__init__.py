from fastapi import APIRouter

from api.routers.v1.admin_catalog import router as admin_catalog_router
from api.routers.v1.auth import router as auth_router
from api.routers.v1.categories import router as categories_router
from api.routers.v1.health import router as health_router
from api.routers.v1.products import router as products_router

v1_router = APIRouter()
v1_router.include_router(health_router)
v1_router.include_router(auth_router, prefix="/api/v1")
v1_router.include_router(categories_router, prefix="/api/v1")
v1_router.include_router(products_router, prefix="/api/v1")
v1_router.include_router(admin_catalog_router, prefix="/api/v1")

__all__ = ["v1_router"]
