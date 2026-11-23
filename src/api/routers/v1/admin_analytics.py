from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db_session
from api.core.security import get_current_user
from api.models.user import User
from api.schemas.analytics import (
    AcquisitionAnalyticsResponse,
    AnalyticsOverviewResponse,
    FunnelAnalyticsResponse,
    ProductAnalyticsResponse,
)
from api.services.analytics import analytics_service

router = APIRouter(prefix="/admin/analytics", tags=["Admin - Analytics"])


@router.get(
    "/overview",
    response_model=AnalyticsOverviewResponse,
    summary="Performance overview (Admin)",
    description="Calculates store revenue, order volume, average order value, returning customer rate, and sales trends.",
)
async def get_overview(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[User, Depends(get_current_user)],
    start_date: Annotated[
        datetime | None, Query(description="Start timestamp (UTC)")
    ] = None,
    end_date: Annotated[
        datetime | None, Query(description="End timestamp (UTC)")
    ] = None,
) -> AnalyticsOverviewResponse:
    return await analytics_service.get_overview(
        db=db,
        start_date=start_date,
        end_date=end_date,
    )


@router.get(
    "/acquisition",
    response_model=AcquisitionAnalyticsResponse,
    summary="Marketing attribution (Admin)",
    description="Traffic source breakdown, channel conversion rates, and UTM campaign sales performance.",
)
async def get_acquisition(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[User, Depends(get_current_user)],
    start_date: Annotated[
        datetime | None, Query(description="Start timestamp (UTC)")
    ] = None,
    end_date: Annotated[
        datetime | None, Query(description="End timestamp (UTC)")
    ] = None,
) -> AcquisitionAnalyticsResponse:
    return await analytics_service.get_acquisition(
        db=db,
        start_date=start_date,
        end_date=end_date,
    )


@router.get(
    "/products",
    response_model=ProductAnalyticsResponse,
    summary="Catalog intelligence (Admin)",
    description="Best-selling items, pre-order campaign progress, and low-inventory warnings.",
)
async def get_product_analytics(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[User, Depends(get_current_user)],
    start_date: Annotated[
        datetime | None, Query(description="Start timestamp (UTC)")
    ] = None,
    end_date: Annotated[
        datetime | None, Query(description="End timestamp (UTC)")
    ] = None,
    limit: Annotated[
        int, Query(ge=1, le=100, description="Maximum items per list")
    ] = 10,
) -> ProductAnalyticsResponse:
    return await analytics_service.get_product_analytics(
        db=db,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )


@router.get(
    "/funnel",
    response_model=FunnelAnalyticsResponse,
    summary="Conversion funnel (Admin)",
    description="End-to-end user conversion pipeline from storefront visit to completed purchase.",
)
async def get_funnel(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[User, Depends(get_current_user)],
    start_date: Annotated[
        datetime | None, Query(description="Start timestamp (UTC)")
    ] = None,
    end_date: Annotated[
        datetime | None, Query(description="End timestamp (UTC)")
    ] = None,
) -> FunnelAnalyticsResponse:
    return await analytics_service.get_funnel(
        db=db,
        start_date=start_date,
        end_date=end_date,
    )
