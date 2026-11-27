import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from api.models.base import Base, UUIDPrimaryKeyMixin


class NotificationChannel(enum.StrEnum):
    """Messaging channels used for alerts."""

    SMS = "sms"
    WHATSAPP = "whatsapp"


class NotificationStatus(enum.StrEnum):
    """Dispatch outcome status."""

    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


class NotificationLog(Base, UUIDPrimaryKeyMixin):
    """Audit log of outbound transactional SMS and WhatsApp notifications."""

    __tablename__ = "notification_logs"

    order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, name="notification_channel", native_enum=False),
        nullable=False,
        index=True,
    )

    recipient: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    message: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus, name="notification_status", native_enum=False),
        default=NotificationStatus.SENT,
        nullable=False,
        index=True,
    )

    provider_response: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
