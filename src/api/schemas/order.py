import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from api.models.order import (
    FulfillmentStatus,
    PaymentMethod,
    PaymentStatus,
    SourceChannel,
)


# ---------------------------------------------------------
# Quote / Checkout Calculation Schemas
# ---------------------------------------------------------
class QuoteItemRequest(BaseModel):
    product_id: uuid.UUID
    variant_id: uuid.UUID | None = None
    quantity: int = Field(gt=0, default=1)


class QuoteRequest(BaseModel):
    items: list[QuoteItemRequest] = Field(min_length=1)
    delivery_region: str = Field(min_length=2, default="Greater Accra")


class QuoteItemResponse(BaseModel):
    product_id: uuid.UUID
    variant_id: uuid.UUID | None = None
    product_name: str
    product_slug: str
    size: str
    color: str
    unit_price: Decimal
    quantity: int
    subtotal: Decimal
    is_pre_order: bool
    in_stock: bool
    error_message: str | None = None


class QuoteResponse(BaseModel):
    items: list[QuoteItemResponse]
    subtotal: Decimal
    delivery_fee: Decimal
    total: Decimal
    is_pre_order: bool
    estimated_dispatch_date: datetime | None = None
    free_delivery_applied: bool = False
    can_checkout: bool = True
    validation_errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------
# Order Creation & Detail Schemas
# ---------------------------------------------------------
class OrderItemCreate(BaseModel):
    product_id: uuid.UUID
    variant_id: uuid.UUID | None = None
    quantity: int = Field(gt=0, default=1)


class OrderCreate(BaseModel):
    customer_name: str = Field(min_length=2, max_length=200)
    customer_phone: str = Field(min_length=9, max_length=50)
    customer_email: EmailStr | None = None

    delivery_region: str = Field(min_length=2, max_length=100)
    delivery_address: str = Field(min_length=3)
    digital_address: str | None = Field(default=None, max_length=50)
    delivery_notes: str | None = None

    payment_method: PaymentMethod = PaymentMethod.MOMO_PAYSTACK
    source_channel: SourceChannel | None = None
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None

    items: list[OrderItemCreate] = Field(min_length=1)


class OrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    variant_id: uuid.UUID | None = None
    product_name: str
    product_slug: str
    image_url: str | None = None
    variant_sku: str | None = None
    size: str
    color: str
    unit_price: Decimal
    quantity: int
    subtotal: Decimal
    is_pre_order: bool


class OrderStatusHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_status: str | None = None
    to_status: str
    notes: str | None = None
    created_at: datetime


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reference: str
    customer_name: str
    customer_phone: str
    customer_email: str | None = None
    delivery_region: str
    delivery_address: str
    digital_address: str | None = None
    delivery_notes: str | None = None
    subtotal: Decimal
    delivery_fee: Decimal
    total: Decimal
    payment_method: PaymentMethod
    payment_status: PaymentStatus
    fulfillment_status: FulfillmentStatus
    is_pre_order: bool
    estimated_dispatch_date: datetime | None = None
    source_channel: SourceChannel | None = None
    items: list[OrderItemResponse] = Field(default_factory=list)
    status_history: list[OrderStatusHistoryResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    page: int
    page_size: int
    pages: int


class OrderStatusUpdate(BaseModel):
    status: FulfillmentStatus
    payment_status: PaymentStatus | None = None
    notes: str | None = None
