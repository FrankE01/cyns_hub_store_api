from fastapi import APIRouter

from api.routers.v1.admin_analytics import router as admin_analytics_router
from api.routers.v1.admin_catalog import router as admin_catalog_router
from api.routers.v1.admin_notifications import (
    router as admin_notifications_router,
)
from api.routers.v1.admin_orders import router as admin_orders_router
from api.routers.v1.admin_payments import router as admin_payments_router
from api.routers.v1.analytics import router as analytics_router
from api.routers.v1.auth import router as auth_router
from api.routers.v1.categories import router as categories_router
from api.routers.v1.checkout import router as checkout_router
from api.routers.v1.health import router as health_router
from api.routers.v1.orders import router as orders_router
from api.routers.v1.payments import router as payments_router
from api.routers.v1.products import router as products_router

v1_router = APIRouter()
v1_router.include_router(health_router)
v1_router.include_router(auth_router, prefix="/api/v1")
v1_router.include_router(categories_router, prefix="/api/v1")
v1_router.include_router(products_router, prefix="/api/v1")
v1_router.include_router(admin_catalog_router, prefix="/api/v1")
v1_router.include_router(checkout_router, prefix="/api/v1")
v1_router.include_router(orders_router, prefix="/api/v1")
v1_router.include_router(admin_orders_router, prefix="/api/v1")
v1_router.include_router(payments_router, prefix="/api/v1")
v1_router.include_router(admin_payments_router, prefix="/api/v1")
v1_router.include_router(analytics_router, prefix="/api/v1")
v1_router.include_router(admin_analytics_router, prefix="/api/v1")
v1_router.include_router(admin_notifications_router, prefix="/api/v1")

__all__ = ["v1_router"]
