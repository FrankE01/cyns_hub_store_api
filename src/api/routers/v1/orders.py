from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db_session
from api.schemas.order import OrderCreate, OrderResponse
from api.services.order import OrderService

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_order(
    payload: OrderCreate,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> OrderResponse:
    """Public customer checkout endpoint to submit a purchase order."""
    order = await OrderService.create_order(db, payload)
    return OrderResponse.model_validate(order)


@router.get("/{reference}", response_model=OrderResponse)
async def track_order(
    reference: str,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    phone: Annotated[
        str | None,
        Query(description="Customer phone number for tracking verification"),
    ] = None,
) -> OrderResponse:
    """Public order tracking endpoint by unique order reference and optional phone verification."""
    order = await OrderService.get_order_by_reference(db, reference, phone=phone)
    return OrderResponse.model_validate(order)
