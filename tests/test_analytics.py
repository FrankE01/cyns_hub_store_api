import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx2 import ASGITransport, AsyncClient

from api.core.config import settings
from api.core.database import get_db_session
from api.core.security import get_current_user
from api.main import app
from api.models.analytics import EventType
from api.models.catalog import PreorderCampaign, ProductVariant
from api.models.order import (
    SourceChannel,
)
from api.models.user import User, UserRole
from api.services.analytics import AnalyticsService


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


# ---------------------------------------------------------------------------
# Unit Tests: Analytics Service IP Hashing & Channel Inference
# ---------------------------------------------------------------------------


def test_ip_hashing_and_channel_inference() -> None:
    """Verify IP hashing produces deterministic SHA-256 and channel inference handles UTM and referrers."""
    ip = "192.168.1.50"
    hash1 = AnalyticsService._hash_ip(ip)
    hash2 = AnalyticsService._hash_ip(ip)
    assert hash1 == hash2
    assert len(hash1) == 64
    assert AnalyticsService._hash_ip(None) is None

    # Channel inference
    assert (
        AnalyticsService._infer_channel(None, "instagram_bio", None)
        == SourceChannel.INSTAGRAM
    )
    assert (
        AnalyticsService._infer_channel(None, None, "https://l.instagram.com/")
        == SourceChannel.INSTAGRAM
    )
    assert (
        AnalyticsService._infer_channel(None, "tiktok_ad", None) == SourceChannel.TIKTOK
    )
    assert (
        AnalyticsService._infer_channel(None, None, "https://api.whatsapp.com/send")
        == SourceChannel.WHATSAPP
    )
    assert AnalyticsService._infer_channel(None, None, None) == SourceChannel.DIRECT
    assert (
        AnalyticsService._infer_channel(SourceChannel.TIKTOK, "instagram", None)
        == SourceChannel.TIKTOK
    )


# ---------------------------------------------------------------------------
# Storefront Event Ingestion Endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_single_event(mock_db: AsyncMock) -> None:
    """Verify POST /api/v1/analytics/events records event and infers channel."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        response = await ac.post(
            f"{settings.api_v1_prefix}/analytics/events",
            json={
                "event_type": "product_view",
                "session_id": "sess_abc123",
                "product_slug": "linen-sundress",
                "utm_source": "instagram_stories",
                "utm_campaign": "black_friday_2026",
                "event_metadata": {"source": "mobile_web"},
            },
        )

    assert response.status_code == 201
    res = response.json()
    assert res["event_type"] == EventType.PRODUCT_VIEW
    assert "id" in res
    assert "created_at" in res
    mock_db.add.assert_called_once()


@pytest.mark.asyncio
async def test_record_batch_events(mock_db: AsyncMock) -> None:
    """Verify POST /api/v1/analytics/events/batch persists multiple interaction events."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        response = await ac.post(
            f"{settings.api_v1_prefix}/analytics/events/batch",
            json={
                "events": [
                    {
                        "event_type": "page_view",
                        "session_id": "sess_batch1",
                        "utm_source": "tiktok",
                    },
                    {
                        "event_type": "add_to_cart",
                        "session_id": "sess_batch1",
                        "product_slug": "silk-wrap-top",
                        "event_metadata": {"quantity": 2},
                    },
                ]
            },
        )

    assert response.status_code == 201
    res = response.json()
    assert len(res) == 2
    assert res[0]["event_type"] == EventType.PAGE_VIEW
    assert res[1]["event_type"] == EventType.ADD_TO_CART
    assert mock_db.add.call_count == 2


# ---------------------------------------------------------------------------
# Admin Analytics Endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_analytics_overview(
    mock_db: AsyncMock,
    admin_user: User,
) -> None:
    """Verify GET /api/v1/admin/analytics/overview computes revenue, volume, and trends."""

    async def _override_user() -> User:
        return admin_user

    app.dependency_overrides[get_current_user] = _override_user

    try:
        # Mock scalar returns for:
        # 1. total_revenue
        # 2. total_orders
        # 3. paid_orders
        # 4. pending_orders
        # 5. cancelled_orders
        # 6. total_customers
        # 7. returning_customers
        # 8. trend_rows
        mock_rev = MagicMock()
        mock_rev.scalar_one.return_value = Decimal("4500.00")

        mock_total_q = MagicMock()
        mock_total_q.scalar_one.return_value = 15

        mock_paid_q = MagicMock()
        mock_paid_q.scalar_one.return_value = 10

        mock_pending_q = MagicMock()
        mock_pending_q.scalar_one.return_value = 3

        mock_cancelled_q = MagicMock()
        mock_cancelled_q.scalar_one.return_value = 2

        mock_cust_total = MagicMock()
        mock_cust_total.scalar_one.return_value = 8

        mock_cust_ret = MagicMock()
        mock_cust_ret.scalar_one.return_value = 2

        mock_trend = MagicMock()
        mock_row = MagicMock()
        mock_row.order_date = "2026-11-22"
        mock_row.revenue = Decimal("1500.00")
        mock_row.orders_count = 3
        mock_trend.all.return_value = [mock_row]

        mock_db.execute.side_effect = [
            mock_rev,
            mock_total_q,
            mock_paid_q,
            mock_pending_q,
            mock_cancelled_q,
            mock_cust_total,
            mock_cust_ret,
            mock_trend,
        ]

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            response = await ac.get(
                f"{settings.api_v1_prefix}/admin/analytics/overview"
            )

        assert response.status_code == 200
        res = response.json()
        assert float(res["total_revenue"]) == 4500.0
        assert res["total_orders"] == 15
        assert res["paid_orders"] == 10
        assert res["pending_orders"] == 3
        assert res["cancelled_orders"] == 2
        assert float(res["average_order_value"]) == 450.0  # 4500 / 10
        assert res["returning_customer_rate"] == 25.0  # 2 / 8 * 100
        assert len(res["sales_trend"]) == 1
        assert res["sales_trend"][0]["date"] == "2026-11-22"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_admin_analytics_acquisition(
    mock_db: AsyncMock,
    admin_user: User,
) -> None:
    """Verify GET /api/v1/admin/analytics/acquisition groups metrics by channel and UTM campaign."""

    async def _override_user() -> User:
        return admin_user

    app.dependency_overrides[get_current_user] = _override_user

    try:
        # 1. Event rows
        mock_ev_res = MagicMock()
        mock_ev_row = MagicMock()
        mock_ev_row.source_channel = SourceChannel.INSTAGRAM
        mock_ev_row.event_type = EventType.PAGE_VIEW
        mock_ev_row.count = 50
        mock_ev_res.all.return_value = [mock_ev_row]

        # 2. Order channel rows
        mock_ord_res = MagicMock()
        mock_ord_row = MagicMock()
        mock_ord_row.source_channel = SourceChannel.INSTAGRAM
        mock_ord_row.orders_count = 5
        mock_ord_row.revenue = Decimal("1250.00")
        mock_ord_res.all.return_value = [mock_ord_row]

        # 3. Campaign rows
        mock_camp_res = MagicMock()
        mock_camp_row = MagicMock()
        mock_camp_row.utm_source = "instagram"
        mock_camp_row.utm_campaign = "summer_drop"
        mock_camp_row.utm_medium = "story"
        mock_camp_row.orders_count = 3
        mock_camp_row.revenue = Decimal("750.00")
        mock_camp_res.all.return_value = [mock_camp_row]

        mock_db.execute.side_effect = [mock_ev_res, mock_ord_res, mock_camp_res]

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            response = await ac.get(
                f"{settings.api_v1_prefix}/admin/analytics/acquisition"
            )

        assert response.status_code == 200
        res = response.json()
        assert "channels" in res
        assert "campaigns" in res

        ig_channel = next(c for c in res["channels"] if c["channel"] == "instagram")
        assert ig_channel["visits"] == 50
        assert ig_channel["orders_count"] == 5
        assert ig_channel["conversion_rate"] == 10.0  # 5 / 50 * 100
        assert float(ig_channel["revenue"]) == 1250.0

        assert len(res["campaigns"]) == 1
        assert res["campaigns"][0]["utm_campaign"] == "summer_drop"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_admin_analytics_products(
    mock_db: AsyncMock,
    admin_user: User,
) -> None:
    """Verify GET /api/v1/admin/analytics/products returns top sellers, preorders, and low-stock alerts."""

    async def _override_user() -> User:
        return admin_user

    app.dependency_overrides[get_current_user] = _override_user

    try:
        # 1. Top sellers
        mock_top = MagicMock()
        mock_top_row = MagicMock()
        mock_top_row.product_name = "Linen Dress"
        mock_top_row.product_slug = "linen-dress"
        mock_top_row.units_sold = 25
        mock_top_row.revenue = Decimal("5000.00")
        mock_top.all.return_value = [mock_top_row]

        # 2. Preorder campaigns
        mock_pre = MagicMock()
        mock_campaign = PreorderCampaign(
            id=uuid.uuid4(),
            product_id=uuid.uuid4(),
            max_order_limit=50,
            current_orders_count=18,
            expected_delivery_date=datetime.now(UTC) + timedelta(days=14),
            is_active=True,
        )
        mock_pre.all.return_value = [(mock_campaign, "Pre-order Blazer")]

        # 3. Low stock variants
        mock_stock = MagicMock()
        mock_variant = ProductVariant(
            id=uuid.uuid4(),
            product_id=uuid.uuid4(),
            sku="BLZ-BLK-S",
            size="S",
            color="Black",
            stock_quantity=2,
            is_active=True,
        )
        mock_stock.all.return_value = [(mock_variant, "Classic Blazer")]

        mock_db.execute.side_effect = [mock_top, mock_pre, mock_stock]

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            response = await ac.get(
                f"{settings.api_v1_prefix}/admin/analytics/products"
            )

        assert response.status_code == 200
        res = response.json()
        assert len(res["top_selling_products"]) == 1
        assert res["top_selling_products"][0]["product_name"] == "Linen Dress"
        assert res["top_selling_products"][0]["units_sold"] == 25

        assert len(res["preorder_performance"]) == 1
        assert res["preorder_performance"][0]["product_name"] == "Pre-order Blazer"
        assert res["preorder_performance"][0]["current_orders"] == 18

        assert len(res["low_stock_alerts"]) == 1
        assert res["low_stock_alerts"][0]["sku"] == "BLZ-BLK-S"
        assert res["low_stock_alerts"][0]["stock_quantity"] == 2
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_admin_analytics_funnel(
    mock_db: AsyncMock,
    admin_user: User,
) -> None:
    """Verify GET /api/v1/admin/analytics/funnel computes step-by-step conversion."""

    async def _override_user() -> User:
        return admin_user

    app.dependency_overrides[get_current_user] = _override_user

    try:
        mock_res = MagicMock()
        row1 = MagicMock(event_type=EventType.PAGE_VIEW, count=1000)
        row2 = MagicMock(event_type=EventType.PRODUCT_VIEW, count=500)
        row3 = MagicMock(event_type=EventType.ADD_TO_CART, count=200)
        row4 = MagicMock(event_type=EventType.CHECKOUT_INITIATED, count=100)
        row5 = MagicMock(event_type=EventType.ORDER_COMPLETED, count=50)
        mock_res.all.return_value = [row1, row2, row3, row4, row5]
        mock_db.execute.return_value = mock_res

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            response = await ac.get(f"{settings.api_v1_prefix}/admin/analytics/funnel")

        assert response.status_code == 200
        res = response.json()
        steps = res["steps"]
        assert len(steps) == 5

        # Storefront visits
        assert steps[0]["count"] == 1000
        assert steps[0]["conversion_from_top"] == 100.0

        # Product views
        assert steps[1]["count"] == 500
        assert steps[1]["conversion_from_previous"] == 50.0
        assert steps[1]["conversion_from_top"] == 50.0

        # Orders completed
        assert steps[4]["count"] == 50
        assert steps[4]["conversion_from_previous"] == 50.0  # 50 / 100
        assert steps[4]["conversion_from_top"] == 5.0  # 50 / 1000
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_admin_analytics_endpoints_require_authentication() -> None:
    """Verify unauthenticated requests to admin analytics endpoints return 401 Unauthorized."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        r1 = await ac.get(f"{settings.api_v1_prefix}/admin/analytics/overview")
        assert r1.status_code == 401

        r2 = await ac.get(f"{settings.api_v1_prefix}/admin/analytics/acquisition")
        assert r2.status_code == 401

        r3 = await ac.get(f"{settings.api_v1_prefix}/admin/analytics/products")
        assert r3.status_code == 401

        r4 = await ac.get(f"{settings.api_v1_prefix}/admin/analytics/funnel")
        assert r4.status_code == 401
