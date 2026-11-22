from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db_session
from api.models.catalog import ProductAvailability
from api.schemas.catalog import ProductListResponse, ProductResponse
from api.services.catalog import CatalogService

router = APIRouter(prefix="/products", tags=["Products"])


@router.get("", response_model=ProductListResponse)
async def list_products(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    category: Annotated[
        str | None,
        Query(description="Filter by category slug"),
    ] = None,
    availability: Annotated[
        ProductAvailability | None,
        Query(description="Filter by availability status"),
    ] = None,
    search: Annotated[
        str | None,
        Query(description="Search term in name or description"),
    ] = None,
    is_featured: Annotated[
        bool | None,
        Query(description="Filter featured items"),
    ] = None,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[
        int,
        Query(ge=1, le=100, description="Items per page"),
    ] = 20,
) -> ProductListResponse:
    """Public endpoint for browsing catalog products with filtering and pagination."""
    return await CatalogService.list_products(
        db=db,
        category_slug=category,
        availability=availability,
        search=search,
        is_featured=is_featured,
        page=page,
        page_size=page_size,
        include_unpublished=False,
    )


@router.get("/{slug}", response_model=ProductResponse)
async def get_product(
    slug: str,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProductResponse:
    """Public endpoint retrieving full product details, variants, images, and pre-order terms."""
    product = await CatalogService.get_product_by_slug(
        db,
        slug=slug,
        include_unpublished=False,
    )
    return ProductResponse.model_validate(product)
