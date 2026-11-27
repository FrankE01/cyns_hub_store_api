import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx2 import ASGITransport, AsyncClient

from api.core.config import settings
from api.core.database import get_db_session
from api.core.security import get_current_user
from api.main import app
from api.models.notification import (
    NotificationChannel,
    NotificationLog,
    NotificationStatus,
)
from api.models.order import (
    FulfillmentStatus,
    Order,
    PaymentMethod,
    PaymentStatus,
)
from api.models.user import User, UserRole
from api.services.notification import NotificationService, notification_service


@pytest.fixture
def mock_db() -> AsyncGenerator[AsyncMock, None]:
    """Dependency override fixture for get_db_session."""
    db = AsyncMock()
    db.add = MagicMock()

    async def _override_get_db() -> AsyncGenerator[AsyncMock, None]:
        yield db

    app.dependency_overrides[get_db_session] = _override_get_db
    yield db
    app.dependency_overrides.pop(get_db_session, None)


@pytest.fixture
def admin_user() -> User:
    """Fixture providing an active administrator user."""
    return User(
        id=uuid.uuid4(),
        email="admin@cynshub.com",
        hashed_password="hash",
        full_name="Admin Cynthia",
        role=UserRole.ADMIN,
        is_active=True,
    )


@pytest.fixture
def sample_order() -> Order:
    """Fixture providing a standard order."""
    return Order(
        id=uuid.uuid4(),
        reference="CYN-20261123-X9Y8",
        customer_name="Serwaa Bonsu",
        customer_phone="0241234567",
        customer_email="serwaa@example.com",
        delivery_region="Greater Accra",
        delivery_address="Airport Residential, Accra",
        subtotal=Decimal("450.00"),
        delivery_fee=Decimal("30.00"),
        total=Decimal("480.00"),
        payment_method=PaymentMethod.MOMO_PAYSTACK,
        payment_status=PaymentStatus.PENDING,
        fulfillment_status=FulfillmentStatus.AWAITING_PAYMENT,
        is_pre_order=False,
    )


# ---------------------------------------------------------------------------
# Unit Tests: Phone Normalization & Gateway Clients
# ---------------------------------------------------------------------------


def test_phone_number_normalization() -> None:
    """Verify Ghanaian phone numbers are normalized to 233XXXXXXXXX for Arkesel."""
    assert NotificationService.normalize_phone_ghana("0241234567") == "233241234567"
    assert NotificationService.normalize_phone_ghana("+233241234567") == "233241234567"
    assert NotificationService.normalize_phone_ghana("233241234567") == "233241234567"
    assert NotificationService.normalize_phone_ghana("0509876543") == "233509876543"
    assert NotificationService.normalize_phone_ghana(" 024 123 4567 ") == "233241234567"


@pytest.mark.asyncio
async def test_send_arkesel_sms_success() -> None:
    """Verify Arkesel SMS client constructs correct payload and headers."""
    service = NotificationService(
        arkesel_api_key="test_api_key",
        arkesel_sender_id="CynsHub",
        arkesel_sms_url="https://sms.arkesel.com/api/v2/sms/send",
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b'{"status":"success"}'
    mock_resp.json.return_value = {
        "status": "success",
        "data": {"id": "msg_123", "credits_used": 1},
    }

    with patch("httpx2.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        result = await service.send_arkesel_sms(
            recipient="0241234567",
            message="Your order CYN-123 is confirmed!",
        )

        assert result["status"] == "sent"
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["headers"]["api-key"] == "test_api_key"
        assert call_kwargs["json"]["sender"] == "CynsHub"
        assert call_kwargs["json"]["recipients"] == ["233241234567"]
        assert "CYN-123" in call_kwargs["json"]["message"]


@pytest.mark.asyncio
async def test_send_arkesel_sms_disabled() -> None:
    """Verify SMS dispatch is cleanly bypassed when notifications are disabled."""
    service = NotificationService()
    original_enabled = settings.notifications.enabled
    settings.notifications.enabled = False

    try:
        with patch("httpx2.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            result = await service.send_arkesel_sms(
                recipient="0241234567",
                message="Test",
            )
            assert result["status"] == "skipped"
            mock_post.assert_not_called()
    finally:
        settings.notifications.enabled = original_enabled


@pytest.mark.asyncio
async def test_send_whatsapp_alert_success() -> None:
    """Verify WhatsApp alert dispatches with Meta Graph API payload structure."""
    service = NotificationService()
    original_wa_enabled = settings.notifications.whatsapp_enabled
    settings.notifications.whatsapp_enabled = True

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b'{"messages":[{"id":"wa_msg_123"}]}'
    mock_resp.json.return_value = {"messages": [{"id": "wa_msg_123"}]}

    try:
        with patch("httpx2.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            result = await service.send_whatsapp(
                recipient="0241234567",
                message="Hello via WhatsApp!",
            )
            assert result["status"] == "sent"
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args[1]
            assert call_kwargs["json"]["messaging_product"] == "whatsapp"
            assert call_kwargs["json"]["to"] == "233241234567"
    finally:
        settings.notifications.whatsapp_enabled = original_wa_enabled


# ---------------------------------------------------------------------------
# Integration Tests: Transactional Alerts & Fail-safe Behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_notify_order_created_triggers_sms_and_log(
    mock_db: AsyncMock,
    sample_order: Order,
) -> None:
    """Verify notify_order_created normalizes phone, sends SMS, and writes NotificationLog."""
    with patch.object(
        notification_service,
        "send_arkesel_sms",
        new_callable=AsyncMock,
    ) as mock_sms:
        mock_sms.return_value = {
            "status": "sent",
            "provider_response": {"id": "sms_001"},
        }

        await notification_service.notify_order_created(mock_db, sample_order)

        mock_sms.assert_called_once()
        call_recipient, call_msg = (
            mock_sms.call_args[1]["recipient"],
            mock_sms.call_args[1]["message"],
        )
        assert call_recipient == sample_order.customer_phone
        assert sample_order.reference in call_msg
        assert "placed" in call_msg
        mock_db.add.assert_called()


@pytest.mark.asyncio
async def test_notify_payment_confirmed_triggers_sms(
    mock_db: AsyncMock,
    sample_order: Order,
) -> None:
    """Verify notify_payment_confirmed dispatches payment confirmation alert."""
    with patch.object(
        notification_service,
        "send_arkesel_sms",
        new_callable=AsyncMock,
    ) as mock_sms:
        mock_sms.return_value = {"status": "sent"}

        await notification_service.notify_payment_confirmed(mock_db, sample_order)

        mock_sms.assert_called_once()
        call_msg = mock_sms.call_args[1]["message"]
        assert "Payment of GHS 480.00" in call_msg
        assert sample_order.reference in call_msg


@pytest.mark.asyncio
async def test_notify_out_for_delivery_and_completed(
    mock_db: AsyncMock,
    sample_order: Order,
) -> None:
    """Verify dispatch and completion notifications build correct messaging."""
    with patch.object(
        notification_service,
        "send_arkesel_sms",
        new_callable=AsyncMock,
    ) as mock_sms:
        mock_sms.return_value = {"status": "sent"}

        await notification_service.notify_out_for_delivery(mock_db, sample_order)
        assert "out for delivery" in mock_sms.call_args[1]["message"]

        await notification_service.notify_order_completed(mock_db, sample_order)
        assert "has been delivered" in mock_sms.call_args[1]["message"]


@pytest.mark.asyncio
async def test_notification_fail_safe_on_network_error(
    mock_db: AsyncMock,
    sample_order: Order,
) -> None:
    """Verify that network exceptions or third-party outages do not raise exceptions."""
    with patch.object(
        notification_service,
        "send_arkesel_sms",
        new_callable=AsyncMock,
        side_effect=Exception("Gateway Timeout"),
    ):
        # Should execute silently without raising uncaught exception
        await notification_service.notify_order_created(mock_db, sample_order)


# ---------------------------------------------------------------------------
# Admin Notification Endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_test_sms_endpoint(
    admin_user: User,
) -> None:
    """Verify POST /api/v1/admin/notifications/test-sms dispatches test SMS when authenticated."""

    async def _override_user() -> User:
        return admin_user

    app.dependency_overrides[get_current_user] = _override_user

    try:
        with patch.object(
            notification_service,
            "send_arkesel_sms",
            new_callable=AsyncMock,
        ) as mock_sms:
            mock_sms.return_value = {
                "status": "sent",
                "provider_response": {"id": "test_1"},
            }

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as ac:
                response = await ac.post(
                    f"{settings.api_v1_prefix}/admin/notifications/test-sms",
                    json={
                        "recipient": "0241234567",
                        "message": "Direct admin test alert",
                    },
                )

            assert response.status_code == 200
            res = response.json()
            assert res["status"] == "sent"
            assert res["channel"] == "sms"
            assert res["recipient"] == "0241234567"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_admin_list_notification_logs(
    mock_db: AsyncMock,
    admin_user: User,
) -> None:
    """Verify GET /api/v1/admin/notifications/logs returns audit log records."""

    async def _override_user() -> User:
        return admin_user

    app.dependency_overrides[get_current_user] = _override_user

    try:
        log = NotificationLog(
            id=uuid.uuid4(),
            channel=NotificationChannel.SMS,
            recipient="233241234567",
            message="Test message",
            status=NotificationStatus.SENT,
            created_at=datetime.now(UTC),
        )

        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 1

        mock_items = MagicMock()
        mock_items.scalars.return_value.all.return_value = [log]

        mock_db.execute.side_effect = [mock_count, mock_items]

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            response = await ac.get(
                f"{settings.api_v1_prefix}/admin/notifications/logs"
            )

        assert response.status_code == 200
        res = response.json()
        assert res["total"] == 1
        assert len(res["items"]) == 1
        assert res["items"][0]["recipient"] == "233241234567"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_admin_notification_endpoints_require_authentication() -> None:
    """Verify unauthenticated requests to admin notification routes are rejected with 401."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        r1 = await ac.post(
            f"{settings.api_v1_prefix}/admin/notifications/test-sms",
            json={"recipient": "0241234567", "message": "Test"},
        )
        assert r1.status_code == 401

        r2 = await ac.get(f"{settings.api_v1_prefix}/admin/notifications/logs")
        assert r2.status_code == 401
