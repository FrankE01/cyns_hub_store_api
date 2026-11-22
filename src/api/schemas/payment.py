import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from api.models.order import PaymentMethod, PaymentStatus


class PaymentInitializeRequest(BaseModel):
    """Payload to initiate a Paystack transaction for an existing order."""

    order_reference: str = Field(
        ...,
        description="The customer's order reference, e.g. CYN-20261122-ABCD",
    )
    callback_url: str | None = Field(
        default=None,
        description="Optional redirect URL after checkout completion",
    )


class PaymentInitializeResponse(BaseModel):
    """Details returned after initializing payment with gateway."""

    payment_id: uuid.UUID
    order_reference: str
    reference: str
    authorization_url: str | None = None
    access_code: str | None = None
    amount: Decimal
    currency: str = "GHS"


class PaymentResponse(BaseModel):
    """Payment transaction details."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_id: uuid.UUID
    order_reference: str | None = None
    amount: Decimal
    currency: str
    payment_method: PaymentMethod
    payment_status: PaymentStatus
    provider: str
    provider_reference: str | None = None
    authorization_url: str | None = None
    customer_phone: str | None = None
    notes: str | None = None
    paid_at: datetime | None = None
    created_at: datetime | None = None
    provider_metadata: dict[str, Any] | None = None


class ManualPaymentSubmitRequest(BaseModel):
    """Customer submission for direct mobile money / bank transfer receipt."""

    order_reference: str = Field(..., description="Order reference")
    transaction_reference: str = Field(
        ...,
        min_length=3,
        max_length=100,
        description="Mobile money transaction ID or deposit reference",
    )
    sender_phone: str | None = Field(
        default=None,
        max_length=50,
        description="Sender MoMo phone number",
    )
    notes: str | None = Field(default=None, description="Optional customer comments")


class ManualPaymentVerifyRequest(BaseModel):
    """Admin payload to verify direct mobile money payment."""

    notes: str | None = Field(
        default=None,
        description="Optional note documenting verification details",
    )


class ManualPaymentRejectRequest(BaseModel):
    """Admin payload to reject an invalid payment claim."""

    reason: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Reason for rejecting the payment claim",
    )


class PaymentListResponse(BaseModel):
    """Paginated list of payment transactions."""

    items: list[PaymentResponse]
    total: int
    page: int
    page_size: int
