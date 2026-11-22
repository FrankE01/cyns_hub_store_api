import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from api.core.config import settings
from api.core.database import get_db_session
from api.core.security import get_current_user
from api.main import app
from api.models.catalog import (
    PreorderCampaign,
    Product,
    ProductAvailability,
    ProductVariant,
)
from api.models.order import (
    FulfillmentStatus,
    Order,
    OrderItem,
    OrderStatusHistory,
    PaymentMethod,
    PaymentStatus,
)
from api.models.user import User, UserRole
from api.schemas.order import OrderStatusUpdate, QuoteRequest
from api.services.order import OrderService


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


@pytest.mark.asyncio
async def test_quote_calculation_accra_and_free_delivery(mock_db: AsyncMock) -> None:
    """Verify delivery fee calculation for Accra and free delivery threshold above 500 GHS."""
    prod_id = uuid.uuid4()
    var_id = uuid.uuid4()
    product = Product(
        id=prod_id,
        name="Linen Sundress",
        slug="linen-sundress",
        description="Summer dress.",
        price=Decimal("200.00"),
        availability_status=ProductAvailability.AVAILABLE,
        is_featured=False,
        variants=[
            ProductVariant(
                id=var_id,
                product_id=prod_id,
                sku="LIN-DRS-S",
                size="S",
                color="Beige",
                color_hex="#F5F5DC",
                stock_quantity=10,
                is_active=True,
            )
        ],
        images=[],
    )

    mock_db.get.return_value = product

    # Case 1: Subtotal 200 (< 500) within Accra -> 25 GHS delivery
    quote1 = await OrderService.calculate_quote(
        mock_db,
        QuoteRequest(
            items=[{"product_id": prod_id, "variant_id": var_id, "quantity": 1}],
            delivery_region="East Legon, Greater Accra",
        ),
    )
    assert quote1.subtotal == Decimal("200.00")
    assert quote1.delivery_fee == Decimal("25.00")
    assert quote1.total == Decimal("225.00")
    assert quote1.free_delivery_applied is False
    assert quote1.can_checkout is True

    # Case 2: Subtotal 600 (>= 500) -> 0 GHS free delivery
    quote2 = await OrderService.calculate_quote(
        mock_db,
        QuoteRequest(
            items=[{"product_id": prod_id, "variant_id": var_id, "quantity": 3}],
            delivery_region="Kumasi, Ashanti Region",
        ),
    )
    assert quote2.subtotal == Decimal("600.00")
    assert quote2.delivery_fee == Decimal("0.00")
    assert quote2.total == Decimal("600.00")
    assert quote2.free_delivery_applied is True


@pytest.mark.asyncio
async def test_quote_out_of_stock_validation(mock_db: AsyncMock) -> None:
    """Verify quote rejects checkout if quantity exceeds available stock."""
    prod_id = uuid.uuid4()
    var_id = uuid.uuid4()
    product = Product(
        id=prod_id,
        name="Limited Silk Scarf",
        slug="limited-silk-scarf",
        description="Pure silk.",
        price=Decimal("150.00"),
        availability_status=ProductAvailability.AVAILABLE,
        is_featured=False,
        variants=[
            ProductVariant(
                id=var_id,
                product_id=prod_id,
                sku="SCF-SLK-01",
                size="OS",
                color="Gold",
                color_hex="#FFD700",
                stock_quantity=2,  # Only 2 available
                is_active=True,
            )
        ],
        images=[],
    )
    mock_db.get.return_value = product

    quote = await OrderService.calculate_quote(
        mock_db,
        QuoteRequest(
            items=[{"product_id": prod_id, "variant_id": var_id, "quantity": 5}],
            delivery_region="Accra",
        ),
    )
    assert quote.can_checkout is False
    assert len(quote.validation_errors) == 1
    assert "insufficient stock" in quote.validation_errors[0].lower()


@pytest.mark.asyncio
async def test_create_order_endpoint(
    async_client: AsyncClient, mock_db: AsyncMock
) -> None:
    """Verify POST /api/v1/orders captures order and deducts variant stock."""
    prod_id = uuid.uuid4()
    var_id = uuid.uuid4()
    variant = ProductVariant(
        id=var_id,
        product_id=prod_id,
        sku="BLZ-BLK-M",
        size="M",
        color="Black",
        color_hex="#000000",
        stock_quantity=10,
        is_active=True,
    )
    product = Product(
        id=prod_id,
        name="Classic Oversized Blazer",
        slug="classic-oversized-blazer",
        description="Tailored oversized blazer.",
        price=Decimal("350.00"),
        availability_status=ProductAvailability.AVAILABLE,
        is_featured=True,
        variants=[variant],
        images=[],
    )

    mock_db.get.return_value = product
    mock_db.scalar.return_value = None  # Reference collision check

    response = await async_client.post(
        f"{settings.api_v1_prefix}/orders",
        json={
            "customer_name": "Ama Serwaa",
            "customer_phone": "+233541234567",
            "customer_email": "ama@example.com",
            "delivery_region": "Greater Accra",
            "delivery_address": "14 Jungle Avenue, East Legon",
            "digital_address": "GA-183-9024",
            "payment_method": "momo_paystack",
            "source_channel": "instagram",
            "items": [
                {
                    "product_id": str(prod_id),
                    "variant_id": str(var_id),
                    "quantity": 2,
                }
            ],
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["reference"].startswith("CYN-")
    assert data["customer_name"] == "Ama Serwaa"
    assert data["subtotal"] == "700.00"
    assert data["delivery_fee"] == "0.00"  # Free delivery threshold exceeded
    assert data["total"] == "700.00"
    assert data["fulfillment_status"] == "awaiting_payment"
    assert len(data["items"]) == 1

    # Verify inventory was deducted from 10 to 8
    assert variant.stock_quantity == 8


@pytest.mark.asyncio
async def test_track_order_by_reference(
    async_client: AsyncClient, mock_db: AsyncMock
) -> None:
    """Verify GET /api/v1/orders/{ref} returns order status and validates phone number."""
    order_id = uuid.uuid4()
    order = Order(
        id=order_id,
        reference="CYN-20261122-TEST",
        customer_name="Kofi Mensah",
        customer_phone="0244123456",
        delivery_region="Greater Accra",
        delivery_address="Spintex Road, Accra",
        subtotal=Decimal("300.00"),
        delivery_fee=Decimal("25.00"),
        total=Decimal("325.00"),
        payment_method=PaymentMethod.DIRECT_MOMO,
        payment_status=PaymentStatus.PENDING,
        fulfillment_status=FulfillmentStatus.AWAITING_PAYMENT,
        is_pre_order=False,
        items=[],
        status_history=[
            OrderStatusHistory(
                id=uuid.uuid4(),
                order_id=order_id,
                from_status=None,
                to_status="awaiting_payment",
                notes="Order placed",
                created_at=datetime.now(UTC),
            )
        ],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = order
    mock_db.execute.return_value = mock_result

    # Successful lookup with matching phone
    res_ok = await async_client.get(
        f"{settings.api_v1_prefix}/orders/CYN-20261122-TEST?phone=0244123456"
    )
    assert res_ok.status_code == 200
    assert res_ok.json()["customer_name"] == "Kofi Mensah"

    # Failed lookup with wrong phone
    res_fail = await async_client.get(
        f"{settings.api_v1_prefix}/orders/CYN-20261122-TEST?phone=0559999999"
    )
    assert res_fail.status_code == 403
    assert "phone number does not match" in res_fail.json()["detail"].lower()


@pytest.mark.asyncio
async def test_admin_order_lifecycle_and_cancellation(
    mock_db: AsyncMock, admin_user: User
) -> None:
    """Verify valid order state transitions, rejection of illegal states, and inventory return on cancel."""
    order_id = uuid.uuid4()
    var_id = uuid.uuid4()
    prod_id = uuid.uuid4()

    variant = ProductVariant(
        id=var_id,
        product_id=prod_id,
        sku="DRS-RED-S",
        size="S",
        color="Red",
        stock_quantity=5,
        is_active=True,
    )

    order = Order(
        id=order_id,
        reference="CYN-20261122-FLOW",
        customer_name="Akosua Mensah",
        customer_phone="0241000000",
        delivery_region="Accra",
        delivery_address="Osu, Accra",
        subtotal=Decimal("200.00"),
        delivery_fee=Decimal("25.00"),
        total=Decimal("225.00"),
        payment_method=PaymentMethod.MOMO_PAYSTACK,
        payment_status=PaymentStatus.PENDING,
        fulfillment_status=FulfillmentStatus.AWAITING_PAYMENT,
        is_pre_order=False,
        items=[
            OrderItem(
                id=uuid.uuid4(),
                order_id=order_id,
                product_id=prod_id,
                variant_id=var_id,
                product_name="Wrap Dress",
                product_slug="wrap-dress",
                size="S",
                color="Red",
                unit_price=Decimal("200.00"),
                quantity=2,
                subtotal=Decimal("200.00"),
                is_pre_order=False,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        ],
        status_history=[],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = order
    mock_db.execute.return_value = mock_result
    mock_db.get.return_value = variant

    # 1. Valid advance: AWAITING_PAYMENT -> PROCESSING
    order = await OrderService.update_order_status(
        mock_db,
        order_id,
        OrderStatusUpdate(
            status=FulfillmentStatus.PROCESSING,
            payment_status=PaymentStatus.PAID,
            notes="Payment received via MoMo",
        ),
        changed_by_user_id=admin_user.id,
    )
    assert order.fulfillment_status == FulfillmentStatus.PROCESSING
    assert order.payment_status == PaymentStatus.PAID
    assert len(order.status_history) == 1

    # 2. Invalid transition: PROCESSING -> AWAITING_PAYMENT (cannot go backward)
    with pytest.raises(Exception) as exc:
        await OrderService.update_order_status(
            mock_db,
            order_id,
            OrderStatusUpdate(status=FulfillmentStatus.AWAITING_PAYMENT),
            changed_by_user_id=admin_user.id,
        )
    assert "cannot transition" in str(exc.value).lower()

    # 3. Cancel order: should return the 2 units to stock (5 + 2 = 7)
    order = await OrderService.update_order_status(
        mock_db,
        order_id,
        OrderStatusUpdate(
            status=FulfillmentStatus.CANCELLED,
            notes="Customer requested cancellation",
        ),
        changed_by_user_id=admin_user.id,
    )
    assert order.fulfillment_status == FulfillmentStatus.CANCELLED
    assert variant.stock_quantity == 7


@pytest.mark.asyncio
async def test_admin_list_orders_endpoint(
    async_client: AsyncClient, mock_db: AsyncMock, admin_user: User
) -> None:
    """Verify GET /api/v1/admin/orders returns paginated orders for administrator."""

    async def _override_user() -> User:
        return admin_user

    app.dependency_overrides[get_current_user] = _override_user

    order = Order(
        id=uuid.uuid4(),
        reference="CYN-20261122-ADM1",
        customer_name="Efua Sutherland",
        customer_phone="0244000111",
        delivery_region="Greater Accra",
        delivery_address="Ridge, Accra",
        subtotal=Decimal("400.00"),
        delivery_fee=Decimal("25.00"),
        total=Decimal("425.00"),
        payment_method=PaymentMethod.MOMO_PAYSTACK,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.PROCESSING,
        is_pre_order=False,
        items=[],
        status_history=[],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    mock_db.scalar.return_value = 1
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [order]
    mock_db.execute.return_value = mock_result

    response = await async_client.get(f"{settings.api_v1_prefix}/admin/orders")
    app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["reference"] == "CYN-20261122-ADM1"
    assert data["items"][0]["fulfillment_status"] == "processing"


@pytest.mark.asyncio
async def test_create_preorder_increments_campaign_count(
    async_client: AsyncClient, mock_db: AsyncMock
) -> None:
    """Verify placing a pre-order increments the campaign's current_orders_count."""
    prod_id = uuid.uuid4()
    var_id = uuid.uuid4()
    deadline = datetime.now(UTC) + timedelta(days=5)
    dispatch = datetime.now(UTC) + timedelta(days=15)

    camp = PreorderCampaign(
        id=uuid.uuid4(),
        product_id=prod_id,
        order_deadline=deadline,
        expected_delivery_date=dispatch,
        max_order_limit=50,
        current_orders_count=10,
        is_active=True,
    )
    product = Product(
        id=prod_id,
        name="Pre-Order Silk Jumpsuit",
        slug="pre-order-silk-jumpsuit",
        description="Silk jumpsuit.",
        price=Decimal("420.00"),
        availability_status=ProductAvailability.PREORDER,
        is_featured=False,
        variants=[
            ProductVariant(
                id=var_id,
                product_id=prod_id,
                sku="JMP-SLK-S",
                size="S",
                color="Navy",
                color_hex="#000080",
                stock_quantity=0,
                is_active=True,
            )
        ],
        images=[],
        preorder_campaign=camp,
    )

    mock_db.get.return_value = product
    mock_db.scalar.return_value = None

    response = await async_client.post(
        f"{settings.api_v1_prefix}/orders",
        json={
            "customer_name": "Yaa Asantewaa",
            "customer_phone": "+233201122334",
            "delivery_region": "Kumasi",
            "delivery_address": "Adum, Kumasi",
            "payment_method": "momo_paystack",
            "items": [
                {
                    "product_id": str(prod_id),
                    "variant_id": str(var_id),
                    "quantity": 3,
                }
            ],
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["is_pre_order"] is True
    assert data["subtotal"] == "1260.00"

    # Verify preorder campaign counter was incremented from 10 to 13
    assert camp.current_orders_count == 13
