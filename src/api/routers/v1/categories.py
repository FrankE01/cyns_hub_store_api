from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db_session
from api.schemas.catalog import CategoryResponse
from api.services.catalog import CatalogService

router = APIRouter(prefix="/categories", tags=["Categories"])


@router.get("", response_model=list[CategoryResponse])
async def list_categories(
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[CategoryResponse]:
    """Public endpoint listing active product categories with product counts."""
    return await CatalogService.list_categories(db, only_active=True)
