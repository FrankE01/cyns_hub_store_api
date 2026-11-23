"""create payment tables

Revision ID: 0004_create_payments
Revises: 0003_create_orders
Create Date: 2026-11-22 17:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004_create_payments"
down_revision: str | None = "0003_create_orders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payments",
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
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column(
            "currency", sa.String(length=10), server_default="GHS", nullable=False
        ),
        sa.Column("payment_method", sa.String(length=50), nullable=False),
        sa.Column(
            "payment_status",
            sa.String(length=50),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_reference", sa.String(length=100), nullable=True),
        sa.Column("access_code", sa.String(length=100), nullable=True),
        sa.Column("authorization_url", sa.Text(), nullable=True),
        sa.Column("customer_phone", sa.String(length=50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "provider_metadata",
            sa.JSON().with_variant(
                postgresql.JSONB(astext_type=sa.Text()), "postgresql"
            ),
            nullable=True,
        ),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
    )

    op.create_index("ix_payments_order_id", "payments", ["order_id"], unique=False)
    op.create_index(
        "ix_payments_payment_status",
        "payments",
        ["payment_status"],
        unique=False,
    )
    op.create_index(
        "ix_payments_provider_reference",
        "payments",
        ["provider_reference"],
        unique=True,
    )
    op.create_index("ix_payments_created_at", "payments", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_payments_created_at", table_name="payments")
    op.drop_index("ix_payments_provider_reference", table_name="payments")
    op.drop_index("ix_payments_payment_status", table_name="payments")
    op.drop_index("ix_payments_order_id", table_name="payments")
    op.drop_table("payments")
