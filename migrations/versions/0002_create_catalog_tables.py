"""create catalog tables

Revision ID: 0002_create_catalog
Revises: 0001_create_users
Create Date: 2026-11-22 13:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_create_catalog"
down_revision: str | None = "0001_create_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Categories Table
    op.create_table(
        "categories",
        sa.Column(
            "id",
            sa.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_categories_slug"), "categories", ["slug"], unique=True)

    # 2. Products Table
    op.create_table(
        "products",
        sa.Column(
            "id",
            sa.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "category_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=250), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column(
            "original_price",
            sa.Numeric(precision=10, scale=2),
            nullable=True,
        ),
        sa.Column(
            "availability_status",
            sa.String(length=20),
            server_default="available",
            nullable=False,
        ),
        sa.Column(
            "is_featured",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column("fit", sa.String(length=255), nullable=True),
        sa.Column("fabric", sa.String(length=255), nullable=True),
        sa.Column("care", sa.String(length=255), nullable=True),
        sa.Column("tags", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("offers", sa.JSON(), server_default="[]", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_products_slug"), "products", ["slug"], unique=True)
    op.create_index(
        op.f("ix_products_category_id"),
        "products",
        ["category_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_products_availability_status"),
        "products",
        ["availability_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_products_is_featured"),
        "products",
        ["is_featured"],
        unique=False,
    )

    # 3. Product Variants Table
    op.create_table(
        "product_variants",
        sa.Column(
            "id",
            sa.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sku", sa.String(length=100), nullable=False),
        sa.Column("size", sa.String(length=20), nullable=False),
        sa.Column("color", sa.String(length=100), nullable=False),
        sa.Column(
            "color_hex", sa.String(length=7), server_default="#000000", nullable=False
        ),
        sa.Column(
            "price_override",
            sa.Numeric(precision=10, scale=2),
            nullable=True,
        ),
        sa.Column("stock_quantity", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_product_variants_sku"), "product_variants", ["sku"], unique=True
    )
    op.create_index(
        op.f("ix_product_variants_product_id"),
        "product_variants",
        ["product_id"],
        unique=False,
    )

    # 4. Product Images Table
    op.create_table(
        "product_images",
        sa.Column(
            "id",
            sa.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column("alt_text", sa.String(length=255), nullable=True),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_product_images_product_id"),
        "product_images",
        ["product_id"],
        unique=False,
    )

    # 5. Preorder Campaigns Table
    op.create_table(
        "preorder_campaigns",
        sa.Column(
            "id",
            sa.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("order_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expected_delivery_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_order_limit", sa.Integer(), nullable=True),
        sa.Column(
            "current_orders_count", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("terms_note", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_preorder_campaigns_product_id"),
        "preorder_campaigns",
        ["product_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("preorder_campaigns")
    op.drop_table("product_images")
    op.drop_table("product_variants")
    op.drop_table("products")
    op.drop_table("categories")
