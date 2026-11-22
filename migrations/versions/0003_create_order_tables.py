"""create order tables

Revision ID: 0003_create_orders
Revises: 0002_create_catalog
Create Date: 2026-11-22 14:55:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_create_orders"
down_revision: str | None = "0002_create_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Orders Table
    op.create_table(
        "orders",
        sa.Column(
            "id",
            sa.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("reference", sa.String(length=50), nullable=False),
        sa.Column("customer_name", sa.String(length=200), nullable=False),
        sa.Column("customer_phone", sa.String(length=50), nullable=False),
        sa.Column("customer_email", sa.String(length=255), nullable=True),
        sa.Column("delivery_region", sa.String(length=100), nullable=False),
        sa.Column("delivery_address", sa.Text(), nullable=False),
        sa.Column("digital_address", sa.String(length=50), nullable=True),
        sa.Column("delivery_notes", sa.Text(), nullable=True),
        sa.Column("subtotal", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("delivery_fee", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("total", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("payment_method", sa.String(length=30), nullable=False),
        sa.Column(
            "payment_status",
            sa.String(length=30),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "fulfillment_status",
            sa.String(length=30),
            server_default="awaiting_payment",
            nullable=False,
        ),
        sa.Column(
            "is_pre_order",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column(
            "estimated_dispatch_date",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("source_channel", sa.String(length=30), nullable=True),
        sa.Column("utm_source", sa.String(length=100), nullable=True),
        sa.Column("utm_medium", sa.String(length=100), nullable=True),
        sa.Column("utm_campaign", sa.String(length=100), nullable=True),
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
    op.create_index(op.f("ix_orders_reference"), "orders", ["reference"], unique=True)
    op.create_index(
        op.f("ix_orders_customer_phone"), "orders", ["customer_phone"], unique=False
    )
    op.create_index(
        op.f("ix_orders_payment_status"), "orders", ["payment_status"], unique=False
    )
    op.create_index(
        op.f("ix_orders_fulfillment_status"),
        "orders",
        ["fulfillment_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_orders_is_pre_order"), "orders", ["is_pre_order"], unique=False
    )

    # 2. Order Items Table
    op.create_table(
        "order_items",
        sa.Column(
            "id",
            sa.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "order_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "variant_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("product_variants.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("product_name", sa.String(length=200), nullable=False),
        sa.Column("product_slug", sa.String(length=250), nullable=False),
        sa.Column("image_url", sa.String(length=1000), nullable=True),
        sa.Column("variant_sku", sa.String(length=100), nullable=True),
        sa.Column("size", sa.String(length=20), nullable=False),
        sa.Column("color", sa.String(length=100), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("subtotal", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("is_pre_order", sa.Boolean(), server_default="false", nullable=False),
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
        op.f("ix_order_items_order_id"), "order_items", ["order_id"], unique=False
    )
    op.create_index(
        op.f("ix_order_items_product_id"), "order_items", ["product_id"], unique=False
    )
    op.create_index(
        op.f("ix_order_items_variant_id"), "order_items", ["variant_id"], unique=False
    )

    # 3. Order Status History Table
    op.create_table(
        "order_status_history",
        sa.Column(
            "id",
            sa.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "order_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_status", sa.String(length=50), nullable=True),
        sa.Column("to_status", sa.String(length=50), nullable=False),
        sa.Column(
            "changed_by_user_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_order_status_history_order_id"),
        "order_status_history",
        ["order_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("order_status_history")
    op.drop_table("order_items")
    op.drop_table("orders")
