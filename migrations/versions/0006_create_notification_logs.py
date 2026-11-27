"""create notification logs table

Revision ID: 0006_create_notifications
Revises: 0005_create_analytics
Create Date: 2026-11-23 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0006_create_notifications"
down_revision: str | None = "0005_create_analytics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_logs",
        sa.Column(
            "id",
            sa.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "order_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("orders.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("recipient", sa.String(length=50), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "provider_response",
            sa.JSON().with_variant(
                postgresql.JSONB(astext_type=sa.Text()), "postgresql"
            ),
            nullable=True,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_logs")),
    )

    op.create_index(
        "ix_notification_logs_order_id",
        "notification_logs",
        ["order_id"],
        unique=False,
    )
    op.create_index(
        "ix_notification_logs_channel",
        "notification_logs",
        ["channel"],
        unique=False,
    )
    op.create_index(
        "ix_notification_logs_recipient",
        "notification_logs",
        ["recipient"],
        unique=False,
    )
    op.create_index(
        "ix_notification_logs_status",
        "notification_logs",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_notification_logs_created_at",
        "notification_logs",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_notification_logs_created_at", table_name="notification_logs")
    op.drop_index("ix_notification_logs_status", table_name="notification_logs")
    op.drop_index("ix_notification_logs_recipient", table_name="notification_logs")
    op.drop_index("ix_notification_logs_channel", table_name="notification_logs")
    op.drop_index("ix_notification_logs_order_id", table_name="notification_logs")
    op.drop_table("notification_logs")
