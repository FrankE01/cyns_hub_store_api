import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from api.models.catalog import ProductAvailability


class ProductDetails(BaseModel):
    """Structured garment garment details."""

    fit: str | None = None
    fabric: str | None = None
    care: str | None = None


# ---------------------------------------------------------
# Category Schemas
# ---------------------------------------------------------
class CategoryBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    slug: str | None = Field(default=None, max_length=120)
    description: str | None = None
    image_url: str | None = None
    display_order: int = 0
    is_active: bool = True


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    slug: str | None = Field(default=None, max_length=120)
    description: str | None = None
    image_url: str | None = None
    display_order: int | None = None
    is_active: bool | None = None


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    description: str | None = None
    image_url: str | None = None
    display_order: int
    is_active: bool
    item_count: int = 0
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------
# Variant Schemas
# ---------------------------------------------------------
class VariantBase(BaseModel):
    sku: str = Field(min_length=1, max_length=100)
    size: str = Field(min_length=1, max_length=20)
    color: str = Field(min_length=1, max_length=100)
    color_hex: str = Field(default="#000000", max_length=7)
    price_override: Decimal | None = None
    stock_quantity: int = Field(default=0, ge=0)
    is_active: bool = True


class VariantCreate(VariantBase):
    pass


class VariantUpdate(BaseModel):
    sku: str | None = None
    size: str | None = None
    color: str | None = None
    color_hex: str | None = None
    price_override: Decimal | None = None
    stock_quantity: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class VariantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    sku: str
    size: str
    color: str
    color_hex: str
    price_override: Decimal | None = None
    stock_quantity: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------
# Image Schemas
# ---------------------------------------------------------
class ImageCreate(BaseModel):
    url: str = Field(min_length=1, max_length=1000)
    alt_text: str | None = None
    display_order: int = 0
    is_primary: bool = False


class ImageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    url: str
    alt_text: str | None = None
    display_order: int
    is_primary: bool
    created_at: datetime


# ---------------------------------------------------------
# Preorder Campaign Schemas
# ---------------------------------------------------------
class PreorderCampaignBase(BaseModel):
    order_deadline: datetime
    expected_delivery_date: datetime
    max_order_limit: int | None = None
    terms_note: str | None = None
    is_active: bool = True


class PreorderCampaignCreate(PreorderCampaignBase):
    pass


class PreorderCampaignUpdate(BaseModel):
    order_deadline: datetime | None = None
    expected_delivery_date: datetime | None = None
    max_order_limit: int | None = None
    terms_note: str | None = None
    is_active: bool | None = None


class PreorderCampaignResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    order_deadline: datetime
    expected_delivery_date: datetime
    max_order_limit: int | None = None
    current_orders_count: int = 0
    terms_note: str | None = None
    is_active: bool
    created_at: datetime


# ---------------------------------------------------------
# Product Schemas
# ---------------------------------------------------------
class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(default=None, max_length=250)
    category_id: uuid.UUID | None = None
    description: str = Field(min_length=1)
    price: Decimal = Field(gt=0)
    original_price: Decimal | None = None
    availability_status: ProductAvailability = ProductAvailability.AVAILABLE
    is_featured: bool = False
    details: ProductDetails | None = None
    tags: list[str] = Field(default_factory=list)
    offers: list[str] = Field(default_factory=list)
    variants: list[VariantCreate] = Field(default_factory=list)
    images: list[ImageCreate] = Field(default_factory=list)
    preorder_campaign: PreorderCampaignCreate | None = None


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    slug: str | None = Field(default=None, max_length=250)
    category_id: uuid.UUID | None = None
    description: str | None = None
    price: Decimal | None = Field(default=None, gt=0)
    original_price: Decimal | None = None
    availability_status: ProductAvailability | None = None
    is_featured: bool | None = None
    details: ProductDetails | None = None
    tags: list[str] | None = None
    offers: list[str] | None = None
    variants: list[VariantCreate] | None = None
    images: list[ImageCreate] | None = None
    preorder_campaign: PreorderCampaignCreate | None = None


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category_id: uuid.UUID | None = None
    category: CategoryResponse | None = None
    name: str
    slug: str
    description: str
    price: Decimal
    original_price: Decimal | None = None
    availability_status: ProductAvailability
    is_featured: bool
    details: ProductDetails
    tags: list[str]
    offers: list[str]
    images: list[ImageResponse]
    variants: list[VariantResponse]
    available_sizes: list[str]
    available_colors: list[dict[str, str]]
    is_pre_order: bool
    preorder_campaign: PreorderCampaignResponse | None = None
    created_at: datetime
    updated_at: datetime


class ProductListResponse(BaseModel):
    items: list[ProductResponse]
    total: int
    page: int
    page_size: int
    pages: int
