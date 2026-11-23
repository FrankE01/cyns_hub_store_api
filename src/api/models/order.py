import enum
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PaymentStatus(enum.StrEnum):
    """Payment transaction status."""

    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"


class FulfillmentStatus(enum.StrEnum):
    """Order processing and delivery lifecycle states."""

    AWAITING_PAYMENT = "awaiting_payment"
    AWAITING_STOCK = "awaiting_stock"
    PROCESSING = "processing"
    READY_FOR_DISPATCH = "ready_for_dispatch"
    OUT_FOR_DELIVERY = "out_for_delivery"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PaymentMethod(enum.StrEnum):
    """Supported payment methods."""

    MOMO_PAYSTACK = "momo_paystack"
    DIRECT_MOMO = "direct_momo"
    BANK_TRANSFER = "bank_transfer"
    CASH_ON_DELIVERY = "cash_on_delivery"


class SourceChannel(enum.StrEnum):
    """Social acquisition and attribution channels."""

    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    WHATSAPP = "whatsapp"
    DIRECT = "direct"


class Order(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Customer purchase order."""

    __tablename__ = "orders"

    reference: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
        nullable=False,
    )

    # Customer Contact Info
    customer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    customer_phone: Mapped[str] = mapped_column(
        String(50),
        index=True,
        nullable=False,
    )
    customer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Delivery Address (Ghana)
    delivery_region: Mapped[str] = mapped_column(String(100), nullable=False)
    delivery_address: Mapped[str] = mapped_column(Text, nullable=False)
    digital_address: Mapped[str | None] = mapped_column(String(50), nullable=True)
    delivery_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Financials (in GHS)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    delivery_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    # Payment & Fulfillment State
    payment_method: Mapped[PaymentMethod] = mapped_column(
        Enum(PaymentMethod, name="payment_method", native_enum=False),
        nullable=False,
    )
    payment_status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status", native_enum=False),
        default=PaymentStatus.PENDING,
        nullable=False,
        index=True,
    )
    fulfillment_status: Mapped[FulfillmentStatus] = mapped_column(
        Enum(FulfillmentStatus, name="fulfillment_status", native_enum=False),
        default=FulfillmentStatus.AWAITING_PAYMENT,
        nullable=False,
        index=True,
    )

    # Pre-order Attributes
    is_pre_order: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )
    estimated_dispatch_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Attribution Marketing Fields
    source_channel: Mapped[SourceChannel | None] = mapped_column(
        Enum(SourceChannel, name="source_channel", native_enum=False),
        nullable=True,
    )
    utm_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    utm_medium: Mapped[str | None] = mapped_column(String(100), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Relationships
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    status_history: Mapped[list["OrderStatusHistory"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="OrderStatusHistory.created_at.asc()",
    )
    payments: Mapped[list["Payment"]] = relationship(  # noqa: F821
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="Payment.created_at.desc()",
    )


class OrderItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Line item within a customer order (price & metadata snapshot)."""

    __tablename__ = "order_items"

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_variants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Historical Snapshots
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    product_slug: Mapped[str] = mapped_column(String(250), nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    variant_sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size: Mapped[str] = mapped_column(String(20), nullable=False)
    color: Mapped[str] = mapped_column(String(100), nullable=False)

    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    is_pre_order: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    order: Mapped["Order"] = relationship(back_populates="items")


class OrderStatusHistory(Base, UUIDPrimaryKeyMixin):
    """Immutable audit trail of order lifecycle state changes."""

    __tablename__ = "order_status_history"

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    to_status: Mapped[str] = mapped_column(String(50), nullable=False)
    changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    order: Mapped["Order"] = relationship(back_populates="status_history")
