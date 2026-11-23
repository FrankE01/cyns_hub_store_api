"""create analytics tables

Revision ID: 0005_create_analytics
Revises: 0004_create_payments
Create Date: 2026-11-23 08:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0005_create_analytics"
down_revision: str | None = "0004_create_payments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analytics_events",
        sa.Column(
            "id",
            sa.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("session_id", sa.String(length=100), nullable=True),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("referrer", sa.String(length=500), nullable=True),
        sa.Column(
            "product_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("product_slug", sa.String(length=250), nullable=True),
        sa.Column(
            "category_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_channel", sa.String(length=50), nullable=True),
        sa.Column("utm_source", sa.String(length=100), nullable=True),
        sa.Column("utm_medium", sa.String(length=100), nullable=True),
        sa.Column("utm_campaign", sa.String(length=100), nullable=True),
        sa.Column("utm_content", sa.String(length=100), nullable=True),
        sa.Column("utm_term", sa.String(length=100), nullable=True),
        sa.Column(
            "event_metadata",
            sa.JSON().with_variant(
                postgresql.JSONB(astext_type=sa.Text()), "postgresql"
            ),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analytics_events")),
    )

    op.create_index(
        "ix_analytics_events_event_type",
        "analytics_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        "ix_analytics_events_session_id",
        "analytics_events",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        "ix_analytics_events_ip_hash", "analytics_events", ["ip_hash"], unique=False
    )
    op.create_index(
        "ix_analytics_events_product_id",
        "analytics_events",
        ["product_id"],
        unique=False,
    )
    op.create_index(
        "ix_analytics_events_source_channel",
        "analytics_events",
        ["source_channel"],
        unique=False,
    )
    op.create_index(
        "ix_analytics_events_utm_source",
        "analytics_events",
        ["utm_source"],
        unique=False,
    )
    op.create_index(
        "ix_analytics_events_utm_campaign",
        "analytics_events",
        ["utm_campaign"],
        unique=False,
    )
    op.create_index(
        "ix_analytics_events_created_at",
        "analytics_events",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_analytics_events_created_at", table_name="analytics_events")
    op.drop_index("ix_analytics_events_utm_campaign", table_name="analytics_events")
    op.drop_index("ix_analytics_events_utm_source", table_name="analytics_events")
    op.drop_index("ix_analytics_events_source_channel", table_name="analytics_events")
    op.drop_index("ix_analytics_events_product_id", table_name="analytics_events")
    op.drop_index("ix_analytics_events_ip_hash", table_name="analytics_events")
    op.drop_index("ix_analytics_events_session_id", table_name="analytics_events")
    op.drop_index("ix_analytics_events_event_type", table_name="analytics_events")
    op.drop_table("analytics_events")
