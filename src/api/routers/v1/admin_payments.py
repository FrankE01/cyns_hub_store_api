import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db_session
from api.core.security import get_current_user
from api.models.order import PaymentStatus
from api.models.user import User
from api.schemas.payment import (
    ManualPaymentRejectRequest,
    ManualPaymentVerifyRequest,
    PaymentListResponse,
    PaymentResponse,
)
from api.services.payment import payment_service

router = APIRouter(prefix="/admin/payments", tags=["Admin - Payments"])


@router.get(
    "",
    response_model=PaymentListResponse,
    summary="List payments (Admin)",
    description="Retrieve paginated list of payment transactions with optional filtering.",
)
async def list_payments(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[User, Depends(get_current_user)],
    status: Annotated[
        PaymentStatus | None, Query(description="Filter by payment status")
    ] = None,
    provider: Annotated[
        str | None, Query(description="Filter by provider (e.g. paystack, manual_momo)")
    ] = None,
    order_id: Annotated[
        uuid.UUID | None, Query(description="Filter by order UUID")
    ] = None,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Page size")] = 20,
) -> PaymentListResponse:
    payments, total = await payment_service.list_payments(
        db=db,
        status_filter=status,
        provider=provider,
        order_id=order_id,
        page=page,
        page_size=page_size,
    )
    return PaymentListResponse(
        items=[PaymentResponse.model_validate(p) for p in payments],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{payment_id}",
    response_model=PaymentResponse,
    summary="Get payment details (Admin)",
    description="Retrieve full details for a single payment transaction.",
)
async def get_payment(
    payment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[User, Depends(get_current_user)],
) -> PaymentResponse:
    payment = await payment_service.get_payment_by_id(db=db, payment_id=payment_id)
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Payment '{payment_id}' not found",
        )
    return PaymentResponse.model_validate(payment)


@router.post(
    "/{payment_id}/verify",
    response_model=PaymentResponse,
    summary="Verify manual payment (Admin)",
    description="Confirm customer's direct MoMo transfer, mark order as paid, and progress order status.",
)
async def verify_manual_payment(
    payment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    payload: ManualPaymentVerifyRequest | None = None,
) -> PaymentResponse:
    notes = payload.notes if payload else None
    payment = await payment_service.verify_manual_payment(
        db=db,
        payment_id=payment_id,
        admin_user=current_user,
        notes=notes,
    )
    return PaymentResponse.model_validate(payment)


@router.post(
    "/{payment_id}/reject",
    response_model=PaymentResponse,
    summary="Reject manual payment (Admin)",
    description="Reject invalid customer payment claim and log reason in order history.",
)
async def reject_manual_payment(
    payment_id: uuid.UUID,
    payload: ManualPaymentRejectRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PaymentResponse:
    payment = await payment_service.reject_manual_payment(
        db=db,
        payment_id=payment_id,
        admin_user=current_user,
        reason=payload.reason,
    )
    return PaymentResponse.model_validate(payment)
