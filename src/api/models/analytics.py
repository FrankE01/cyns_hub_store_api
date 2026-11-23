import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from api.models.base import Base, UUIDPrimaryKeyMixin
from api.models.order import SourceChannel


class EventType(enum.StrEnum):
    """Core customer journey and funnel event types."""

    PAGE_VIEW = "page_view"
    PRODUCT_VIEW = "product_view"
    ADD_TO_CART = "add_to_cart"
    CHECKOUT_INITIATED = "checkout_initiated"
    ORDER_COMPLETED = "order_completed"


class AnalyticsEvent(Base, UUIDPrimaryKeyMixin):
    """Event log capturing storefront customer interactions, funnel milestones, and marketing attribution."""

    __tablename__ = "analytics_events"

    event_type: Mapped[EventType] = mapped_column(
        Enum(EventType, name="analytics_event_type", native_enum=False),
        nullable=False,
        index=True,
    )

    # User & Session Identification
    session_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    referrer: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Product / Category References
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    product_slug: Mapped[str | None] = mapped_column(String(250), nullable=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Attribution & UTM Tracking
    source_channel: Mapped[SourceChannel | None] = mapped_column(
        Enum(SourceChannel, name="source_channel", native_enum=False),
        nullable=True,
        index=True,
    )
    utm_source: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )
    utm_medium: Mapped[str | None] = mapped_column(String(100), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )
    utm_content: Mapped[str | None] = mapped_column(String(100), nullable=True)
    utm_term: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Payload & Event Properties
    event_metadata: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
