import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from api.models.notification import NotificationChannel, NotificationStatus


class TestSMSRequest(BaseModel):
    """Payload to trigger a test SMS dispatch."""

    recipient: str = Field(
        ...,
        min_length=9,
        max_length=50,
        description="Ghanaian or international phone number (e.g. 0241234567 or +233241234567)",
    )
    message: str = Field(
        default="Hello from Cyn's Hub! This is a test notification.",
        min_length=1,
        max_length=500,
        description="Message content",
    )


class TestWhatsAppRequest(BaseModel):
    """Payload to trigger a test WhatsApp dispatch."""

    recipient: str = Field(
        ...,
        min_length=9,
        max_length=50,
        description="WhatsApp phone number with country code",
    )
    message: str = Field(
        default="Hello from Cyn's Hub! This is a test WhatsApp alert.",
        min_length=1,
        max_length=1000,
        description="Message content",
    )


class NotificationDispatchResponse(BaseModel):
    """Outcome of an SMS or WhatsApp dispatch."""

    status: str
    channel: str
    recipient: str
    message: str
    provider_response: dict[str, Any] | None = None


class NotificationLogResponse(BaseModel):
    """Notification audit record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_id: uuid.UUID | None = None
    channel: NotificationChannel
    recipient: str
    message: str
    status: NotificationStatus
    created_at: datetime
    error_message: str | None = None
    provider_response: dict[str, Any] | None = None


class NotificationLogListResponse(BaseModel):
    """Paginated list of notification audit records."""

    items: list[NotificationLogResponse]
    total: int
    page: int
    page_size: int
