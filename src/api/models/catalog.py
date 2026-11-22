import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ProductAvailability(enum.StrEnum):
    """Product availability state in store."""

    AVAILABLE = "available"
    PREORDER = "preorder"
    SOLD_OUT = "sold_out"
    UNPUBLISHED = "unpublished"


class Category(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Product category hierarchy."""

    __tablename__ = "categories"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(120),
        unique=True,
        index=True,
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    products: Mapped[list["Product"]] = relationship(
        back_populates="category",
        lazy="selectin",
    )


class Product(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Core fashion apparel product listing."""

    __tablename__ = "products"

    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(250),
        unique=True,
        index=True,
        nullable=False,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    original_price: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )
    availability_status: Mapped[ProductAvailability] = mapped_column(
        Enum(ProductAvailability, name="product_availability", native_enum=False),
        default=ProductAvailability.AVAILABLE,
        nullable=False,
        index=True,
    )
    is_featured: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )

    fit: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fabric: Mapped[str | None] = mapped_column(String(255), nullable=True)
    care: Mapped[str | None] = mapped_column(String(255), nullable=True)

    tags: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=list,
        nullable=False,
    )
    offers: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=list,
        nullable=False,
    )

    category: Mapped["Category | None"] = relationship(
        back_populates="products",
        lazy="selectin",
    )
    variants: Mapped[list["ProductVariant"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ProductVariant.size",
    )
    images: Mapped[list["ProductImage"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ProductImage.display_order",
    )
    preorder_campaign: Mapped["PreorderCampaign | None"] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="selectin",
    )

    @property
    def is_pre_order(self) -> bool:
        """Determines if the product is configured as a pre-order item."""
        if self.availability_status == ProductAvailability.PREORDER:
            return True
        return bool(self.preorder_campaign and self.preorder_campaign.is_active)

    @property
    def details(self) -> dict[str, str | None]:
        """Provides structured fit, fabric, and care details."""
        return {
            "fit": self.fit,
            "fabric": self.fabric,
            "care": self.care,
        }

    @property
    def available_sizes(self) -> list[str]:
        """List of active sizes with inventory or available under pre-order."""
        seen: set[str] = set()
        sizes: list[str] = []
        for variant in self.variants:
            if (
                variant.is_active
                and (variant.stock_quantity > 0 or self.is_pre_order)
                and variant.size not in seen
            ):
                seen.add(variant.size)
                sizes.append(variant.size)
        return sizes

    @property
    def available_colors(self) -> list[dict[str, str]]:
        """List of distinct color names and hex codes."""
        seen: set[tuple[str, str]] = set()
        colors: list[dict[str, str]] = []
        for variant in self.variants:
            key = (variant.color, variant.color_hex)
            if (
                variant.is_active
                and (variant.stock_quantity > 0 or self.is_pre_order)
                and key not in seen
            ):
                seen.add(key)
                colors.append({"name": variant.color, "hex": variant.color_hex})
        return colors


class ProductVariant(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Specific size and color SKU for a product."""

    __tablename__ = "product_variants"

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sku: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
    )
    size: Mapped[str] = mapped_column(String(20), nullable=False)
    color: Mapped[str] = mapped_column(String(100), nullable=False)
    color_hex: Mapped[str] = mapped_column(String(7), default="#000000", nullable=False)
    price_override: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )
    stock_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    product: Mapped["Product"] = relationship(back_populates="variants")


class ProductImage(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Product photography image asset."""

    __tablename__ = "product_images"

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    alt_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    product: Mapped["Product"] = relationship(back_populates="images")


class PreorderCampaign(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Pre-order sales batch rules, cutoffs, and delivery expectations."""

    __tablename__ = "preorder_campaigns"

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    order_deadline: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    expected_delivery_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    max_order_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_orders_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    terms_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    product: Mapped["Product"] = relationship(back_populates="preorder_campaign")
