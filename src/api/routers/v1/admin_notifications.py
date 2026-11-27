import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db_session
from api.core.security import get_current_user
from api.models.notification import NotificationChannel
from api.models.user import User
from api.schemas.notification import (
    NotificationDispatchResponse,
    NotificationLogListResponse,
    NotificationLogResponse,
    TestSMSRequest,
    TestWhatsAppRequest,
)
from api.services.notification import notification_service

router = APIRouter(prefix="/admin/notifications", tags=["Admin - Notifications"])


@router.post(
    "/test-sms",
    response_model=NotificationDispatchResponse,
    status_code=status.HTTP_200_OK,
    summary="Test Arkesel SMS dispatch",
    description="Sends a test transactional SMS message to verify Arkesel API credentials.",
)
async def test_sms(
    payload: TestSMSRequest,
    _: Annotated[User, Depends(get_current_user)],
) -> NotificationDispatchResponse:
    result = await notification_service.send_arkesel_sms(
        recipient=payload.recipient,
        message=payload.message,
    )
    return NotificationDispatchResponse(
        status=result.get("status", "unknown"),
        channel="sms",
        recipient=payload.recipient,
        message=payload.message,
        provider_response=result.get("provider_response"),
    )


@router.post(
    "/test-whatsapp",
    response_model=NotificationDispatchResponse,
    status_code=status.HTTP_200_OK,
    summary="Test WhatsApp dispatch",
    description="Sends a test WhatsApp message to verify Meta / Arkesel WhatsApp credentials.",
)
async def test_whatsapp(
    payload: TestWhatsAppRequest,
    _: Annotated[User, Depends(get_current_user)],
) -> NotificationDispatchResponse:
    result = await notification_service.send_whatsapp(
        recipient=payload.recipient,
        message=payload.message,
    )
    return NotificationDispatchResponse(
        status=result.get("status", "unknown"),
        channel="whatsapp",
        recipient=payload.recipient,
        message=payload.message,
        provider_response=result.get("provider_response"),
    )


@router.get(
    "/logs",
    response_model=NotificationLogListResponse,
    summary="List notification logs (Admin)",
    description="Inspect audit history of transactional SMS and WhatsApp alerts.",
)
async def list_notification_logs(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[User, Depends(get_current_user)],
    channel: Annotated[
        NotificationChannel | None, Query(description="Filter by channel")
    ] = None,
    recipient: Annotated[
        str | None, Query(description="Filter by recipient phone number")
    ] = None,
    order_id: Annotated[
        uuid.UUID | None, Query(description="Filter by order UUID")
    ] = None,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Page size")] = 20,
) -> NotificationLogListResponse:
    logs, total = await notification_service.list_logs(
        db=db,
        channel=channel,
        recipient=recipient,
        order_id=order_id,
        page=page,
        page_size=page_size,
    )
    return NotificationLogListResponse(
        items=[NotificationLogResponse.model_validate(log) for log in logs],
        total=total,
        page=page,
        page_size=page_size,
    )
