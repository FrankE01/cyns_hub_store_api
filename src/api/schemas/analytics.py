import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from api.models.analytics import EventType
from api.models.order import SourceChannel

# ---------------------------------------------------------------------------
# Event Ingestion Contracts
# ---------------------------------------------------------------------------


class EventCreate(BaseModel):
    """Payload for capturing a single storefront analytics event."""

    event_type: EventType
    session_id: str | None = Field(default=None, max_length=100)
    product_id: uuid.UUID | None = None
    product_slug: str | None = Field(default=None, max_length=250)
    category_id: uuid.UUID | None = None
    source_channel: SourceChannel | None = None
    utm_source: str | None = Field(default=None, max_length=100)
    utm_medium: str | None = Field(default=None, max_length=100)
    utm_campaign: str | None = Field(default=None, max_length=100)
    utm_content: str | None = Field(default=None, max_length=100)
    utm_term: str | None = Field(default=None, max_length=100)
    referrer: str | None = Field(default=None, max_length=500)
    event_metadata: dict[str, Any] | None = None


class EventBatchCreate(BaseModel):
    """Payload for batching multiple storefront interactions in a single request."""

    events: list[EventCreate] = Field(min_length=1, max_length=100)


class EventResponse(BaseModel):
    """Event ingestion confirmation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: EventType
    created_at: datetime


# ---------------------------------------------------------------------------
# Reporting & Aggregations Contracts
# ---------------------------------------------------------------------------


class SalesTrendBucket(BaseModel):
    """Daily revenue and volume aggregation bucket."""

    date: str
    revenue: Decimal
    orders_count: int


class AnalyticsOverviewResponse(BaseModel):
    """Executive summary of store performance and revenue."""

    period_start: datetime
    period_end: datetime
    total_revenue: Decimal
    total_orders: int
    paid_orders: int
    pending_orders: int
    cancelled_orders: int
    average_order_value: Decimal
    returning_customer_rate: float
    sales_trend: list[SalesTrendBucket]


class AcquisitionChannelResponse(BaseModel):
    """Channel traffic and conversion metrics."""

    channel: str
    visits: int
    product_views: int
    add_to_cart_count: int
    checkout_initiated_count: int
    orders_count: int
    revenue: Decimal
    conversion_rate: float


class CampaignAttributionResponse(BaseModel):
    """UTM Campaign tracking and attribution metrics."""

    utm_source: str | None = None
    utm_campaign: str | None = None
    utm_medium: str | None = None
    visits: int
    orders_count: int
    revenue: Decimal


class AcquisitionAnalyticsResponse(BaseModel):
    """Acquisition and marketing channel performance summary."""

    period_start: datetime
    period_end: datetime
    channels: list[AcquisitionChannelResponse]
    campaigns: list[CampaignAttributionResponse]


class TopSellingProductResponse(BaseModel):
    """Product sales performance metrics."""

    product_id: uuid.UUID
    product_name: str
    product_slug: str
    units_sold: int
    revenue: Decimal


class PreorderPerformanceResponse(BaseModel):
    """Pre-order campaign target vs order progress."""

    product_id: uuid.UUID
    product_name: str
    campaign_target: int | None = None
    current_orders: int
    expected_dispatch_date: datetime | None = None


class LowStockVariantResponse(BaseModel):
    """Inventory depletion warning."""

    variant_id: uuid.UUID
    product_name: str
    sku: str
    size: str
    color: str
    stock_quantity: int


class ProductAnalyticsResponse(BaseModel):
    """Catalog intelligence: top sellers, pre-order campaigns, and inventory alerts."""

    period_start: datetime
    period_end: datetime
    top_selling_products: list[TopSellingProductResponse]
    preorder_performance: list[PreorderPerformanceResponse]
    low_stock_alerts: list[LowStockVariantResponse]


class FunnelStepResponse(BaseModel):
    """Single step in the conversion funnel."""

    step: str
    count: int
    conversion_from_previous: float
    conversion_from_top: float


class FunnelAnalyticsResponse(BaseModel):
    """End-to-end customer conversion funnel."""

    period_start: datetime
    period_end: datetime
    steps: list[FunnelStepResponse]
