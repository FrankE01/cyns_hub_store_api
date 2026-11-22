import json
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db_session
from api.schemas.payment import (
    ManualPaymentSubmitRequest,
    PaymentInitializeRequest,
    PaymentInitializeResponse,
    PaymentResponse,
)
from api.services.payment import payment_service
from api.services.paystack import PaystackService

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post(
    "/initialize",
    response_model=PaymentInitializeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initialize Paystack payment",
    description="Initiates an online payment transaction for an existing order.",
)
async def initialize_payment(
    payload: PaymentInitializeRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> PaymentInitializeResponse:
    payment = await payment_service.initialize_paystack_payment(
        db=db,
        order_reference=payload.order_reference,
        callback_url=payload.callback_url,
    )
    return PaymentInitializeResponse(
        payment_id=payment.id,
        order_reference=payload.order_reference,
        reference=payment.provider_reference or "",
        authorization_url=payment.authorization_url,
        access_code=payment.access_code,
        amount=payment.amount,
        currency=payment.currency,
    )


@router.get(
    "/verify/{reference}",
    response_model=PaymentResponse,
    summary="Verify Paystack transaction",
    description="Polls or validates transaction outcome with Paystack upon return to storefront.",
)
async def verify_payment(
    reference: str,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> PaymentResponse:
    payment = await payment_service.verify_paystack_payment(db=db, reference=reference)
    return PaymentResponse.model_validate(payment)


@router.post(
    "/webhook",
    status_code=status.HTTP_200_OK,
    summary="Paystack webhook endpoint",
    description="Cryptographically verified webhook handler for Paystack charge events.",
)
async def paystack_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    x_paystack_signature: Annotated[
        str | None, Header(alias="x-paystack-signature")
    ] = None,
) -> dict[str, str]:
    raw_body = await request.body()

    is_valid = PaystackService.verify_webhook_signature(
        payload_bytes=raw_body,
        signature_header=x_paystack_signature,
    )
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Paystack signature header",
        )

    try:
        event_payload = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        ) from exc

    await payment_service.process_paystack_webhook(db=db, event_payload=event_payload)
    return {"status": "success", "message": "Webhook processed successfully"}


@router.post(
    "/manual-submit",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit direct Mobile Money receipt",
    description="Customer submits MoMo transaction ID or cash deposit reference for manual verification.",
)
async def submit_manual_payment(
    payload: ManualPaymentSubmitRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> PaymentResponse:
    payment = await payment_service.submit_manual_payment(
        db=db,
        order_reference=payload.order_reference,
        transaction_reference=payload.transaction_reference,
        sender_phone=payload.sender_phone,
        notes=payload.notes,
    )
    return PaymentResponse.model_validate(payment)
