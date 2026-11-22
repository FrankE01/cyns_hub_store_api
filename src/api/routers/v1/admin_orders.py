import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db_session
from api.core.security import get_current_user
from api.models.order import FulfillmentStatus, PaymentStatus
from api.models.user import User
from api.schemas.order import OrderListResponse, OrderResponse, OrderStatusUpdate
from api.services.order import OrderService

router = APIRouter(prefix="/admin/orders", tags=["Admin Orders"])


@router.get("", response_model=OrderListResponse)
async def admin_list_orders(
    _: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    status: Annotated[FulfillmentStatus | None, Query()] = None,
    payment_status: Annotated[PaymentStatus | None, Query()] = None,
    is_pre_order: Annotated[bool | None, Query()] = None,
    search: Annotated[
        str | None, Query(description="Search reference, customer, or phone")
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> OrderListResponse:
    """Admin endpoint to search, filter, and paginate through customer orders."""
    return await OrderService.list_orders(
        db=db,
        fulfillment_status=status,
        payment_status=payment_status,
        is_pre_order=is_pre_order,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.get("/{order_id}", response_model=OrderResponse)
async def admin_get_order(
    order_id: uuid.UUID,
    _: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> OrderResponse:
    """Admin endpoint to retrieve a single order with item history and delivery details."""
    order = await OrderService.get_order_by_id(db, order_id)
    return OrderResponse.model_validate(order)


@router.patch("/{order_id}/status", response_model=OrderResponse)
async def admin_update_order_status(
    order_id: uuid.UUID,
    payload: OrderStatusUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> OrderResponse:
    """Admin endpoint to advance order state machine, update payment, or cancel order."""
    order = await OrderService.update_order_status(
        db=db,
        order_id=order_id,
        payload=payload,
        changed_by_user_id=current_user.id,
    )
    return OrderResponse.model_validate(order)
