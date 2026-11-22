import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db_session
from api.core.security import get_current_admin, get_current_user
from api.models.catalog import ProductAvailability
from api.models.user import User
from api.schemas.catalog import (
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
    ProductCreate,
    ProductListResponse,
    ProductResponse,
    ProductUpdate,
)
from api.services.catalog import CatalogService

router = APIRouter(prefix="/admin", tags=["Admin Catalog"])


# ---------------------------------------------------------
# Admin Category Routes
# ---------------------------------------------------------
@router.get("/categories", response_model=list[CategoryResponse])
async def admin_list_categories(
    _: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[CategoryResponse]:
    """Admin endpoint listing all categories including inactive ones."""
    return await CatalogService.list_categories(db, only_active=False)


@router.post(
    "/categories",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def admin_create_category(
    payload: CategoryCreate,
    _: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> CategoryResponse:
    """Admin endpoint creating a new catalog category."""
    category = await CatalogService.create_category(db, payload)
    return CategoryResponse.model_validate(category)


@router.patch("/categories/{category_id}", response_model=CategoryResponse)
async def admin_update_category(
    category_id: uuid.UUID,
    payload: CategoryUpdate,
    _: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> CategoryResponse:
    """Admin endpoint updating an existing catalog category."""
    category = await CatalogService.update_category(db, category_id, payload)
    return CategoryResponse.model_validate(category)


@router.delete(
    "/categories/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def admin_delete_category(
    category_id: uuid.UUID,
    _: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> None:
    """Admin-only endpoint deleting a catalog category."""
    await CatalogService.delete_category(db, category_id)


# ---------------------------------------------------------
# Admin Product Routes
# ---------------------------------------------------------
@router.get("/products", response_model=ProductListResponse)
async def admin_list_products(
    _: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    category: Annotated[str | None, Query()] = None,
    availability: Annotated[ProductAvailability | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    is_featured: Annotated[bool | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ProductListResponse:
    """Admin endpoint listing all products, including unpublished and draft items."""
    return await CatalogService.list_products(
        db=db,
        category_slug=category,
        availability=availability,
        search=search,
        is_featured=is_featured,
        page=page,
        page_size=page_size,
        include_unpublished=True,
    )


@router.get("/products/{product_id}", response_model=ProductResponse)
async def admin_get_product(
    product_id: uuid.UUID,
    _: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProductResponse:
    """Admin endpoint retrieving any product by UUID."""
    product = await CatalogService.get_product_by_id(db, product_id)
    return ProductResponse.model_validate(product)


@router.post(
    "/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
)
async def admin_create_product(
    payload: ProductCreate,
    _: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProductResponse:
    """Admin endpoint creating a product with variants, imagery, and pre-order settings."""
    product = await CatalogService.create_product(db, payload)
    return ProductResponse.model_validate(product)


@router.patch("/products/{product_id}", response_model=ProductResponse)
async def admin_update_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    _: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProductResponse:
    """Admin endpoint updating product details, variants, or pre-order settings."""
    product = await CatalogService.update_product(db, product_id, payload)
    return ProductResponse.model_validate(product)


@router.delete(
    "/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def admin_delete_product(
    product_id: uuid.UUID,
    _: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> None:
    """Admin-only endpoint deleting a product and its cascade children."""
    await CatalogService.delete_product(db, product_id)
