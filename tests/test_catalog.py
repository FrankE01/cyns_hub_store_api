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
    Category,
    PreorderCampaign,
    Product,
    ProductAvailability,
    ProductImage,
    ProductVariant,
)
from api.models.user import User, UserRole


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
def staff_user() -> User:
    """Fixture providing an active staff user."""
    return User(
        id=uuid.uuid4(),
        email="staff@cynshub.com",
        hashed_password="hash",
        full_name="Staff Member",
        role=UserRole.STAFF,
        is_active=True,
    )


def test_product_model_properties() -> None:
    """Unit test for Product computed properties: is_pre_order, details, available_sizes, available_colors."""
    prod_id = uuid.uuid4()
    product = Product(
        id=prod_id,
        name="Silk Evening Gown",
        slug="silk-evening-gown",
        description="Luxurious emerald silk gown.",
        price=Decimal("450.00"),
        availability_status=ProductAvailability.AVAILABLE,
        is_featured=True,
        fit="Regular fit, floor length",
        fabric="100% Mulberry Silk",
        care="Dry clean only",
        tags=["Bestseller", "New Arrival"],
        offers=["Free Delivery in Accra"],
    )

    v1 = ProductVariant(
        id=uuid.uuid4(),
        product_id=prod_id,
        sku="CYN-GWN-EMR-S",
        size="S",
        color="Emerald Green",
        color_hex="#046307",
        stock_quantity=5,
        is_active=True,
    )
    v2 = ProductVariant(
        id=uuid.uuid4(),
        product_id=prod_id,
        sku="CYN-GWN-EMR-M",
        size="M",
        color="Emerald Green",
        color_hex="#046307",
        stock_quantity=0,  # Out of stock
        is_active=True,
    )
    product.variants = [v1, v2]

    assert product.is_pre_order is False
    assert product.details == {
        "fit": "Regular fit, floor length",
        "fabric": "100% Mulberry Silk",
        "care": "Dry clean only",
    }
    # Only size S should be available because M has 0 stock and is not pre-order
    assert product.available_sizes == ["S"]
    assert product.available_colors == [{"name": "Emerald Green", "hex": "#046307"}]

    # Now make it a pre-order item: out-of-stock sizes should become available for pre-order
    product.availability_status = ProductAvailability.PREORDER
    assert product.is_pre_order is True
    assert set(product.available_sizes) == {"S", "M"}


@pytest.mark.asyncio
async def test_storefront_list_categories(
    async_client: AsyncClient, mock_db: AsyncMock
) -> None:
    """Verify GET /api/v1/categories returns categories with product count."""
    cat1 = Category(
        id=uuid.uuid4(),
        name="Dresses",
        slug="dresses",
        description="Formal and casual dresses.",
        display_order=1,
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    mock_result = MagicMock()
    mock_result.all.return_value = [(cat1, 8)]
    mock_db.execute.return_value = mock_result

    response = await async_client.get(f"{settings.api_v1_prefix}/categories")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Dresses"
    assert data[0]["slug"] == "dresses"
    assert data[0]["item_count"] == 8


@pytest.mark.asyncio
async def test_storefront_list_products(
    async_client: AsyncClient, mock_db: AsyncMock
) -> None:
    """Verify GET /api/v1/products returns paginated product listings."""
    prod = Product(
        id=uuid.uuid4(),
        name="Linen Summer Dress",
        slug="linen-summer-dress",
        description="Breezy lightweight dress.",
        price=Decimal("220.00"),
        availability_status=ProductAvailability.AVAILABLE,
        is_featured=True,
        fit="Loose fit",
        fabric="100% Linen",
        care="Machine wash cold",
        tags=["Summer"],
        offers=[],
        variants=[],
        images=[],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    mock_db.scalar.return_value = 1  # count = 1
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [prod]
    mock_db.execute.return_value = mock_result

    response = await async_client.get(f"{settings.api_v1_prefix}/products")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["page"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "Linen Summer Dress"
    assert data["items"][0]["slug"] == "linen-summer-dress"


@pytest.mark.asyncio
async def test_storefront_get_product_by_slug(
    async_client: AsyncClient, mock_db: AsyncMock
) -> None:
    """Verify GET /api/v1/products/{slug} returns product with variants and pre-order info."""
    prod_id = uuid.uuid4()
    deadline = datetime.now(UTC) + timedelta(days=7)
    dispatch = datetime.now(UTC) + timedelta(days=14)

    prod = Product(
        id=prod_id,
        name="Pre-Order Maxi Set",
        slug="pre-order-maxi-set",
        description="Two-piece matching set.",
        price=Decimal("380.00"),
        availability_status=ProductAvailability.PREORDER,
        is_featured=False,
        fit="Regular",
        fabric="Cotton blend",
        care="Dry clean",
        tags=["Pre-Order"],
        offers=[],
        variants=[
            ProductVariant(
                id=uuid.uuid4(),
                product_id=prod_id,
                sku="SET-BLK-S",
                size="S",
                color="Black",
                color_hex="#000000",
                stock_quantity=0,
                is_active=True,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        ],
        images=[
            ProductImage(
                id=uuid.uuid4(),
                product_id=prod_id,
                url="https://images.unsplash.com/photo-example.jpg",
                alt_text="Front view",
                display_order=0,
                is_primary=True,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        ],
        preorder_campaign=PreorderCampaign(
            id=uuid.uuid4(),
            product_id=prod_id,
            order_deadline=deadline,
            expected_delivery_date=dispatch,
            max_order_limit=50,
            current_orders_count=12,
            terms_note="Ships within 2 weeks of campaign close.",
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = prod
    mock_db.execute.return_value = mock_result

    response = await async_client.get(
        f"{settings.api_v1_prefix}/products/pre-order-maxi-set"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Pre-Order Maxi Set"
    assert data["is_pre_order"] is True
    assert data["preorder_campaign"] is not None
    assert data["preorder_campaign"]["current_orders_count"] == 12
    assert len(data["variants"]) == 1
    assert len(data["images"]) == 1


@pytest.mark.asyncio
async def test_storefront_get_product_not_found(
    async_client: AsyncClient, mock_db: AsyncMock
) -> None:
    """Verify non-existent product slug returns 404 Not Found."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    response = await async_client.get(
        f"{settings.api_v1_prefix}/products/non-existent-product"
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_admin_create_category(
    async_client: AsyncClient, mock_db: AsyncMock, admin_user: User
) -> None:
    """Verify POST /api/v1/admin/categories creates a new category."""

    async def _override_user() -> User:
        return admin_user

    app.dependency_overrides[get_current_user] = _override_user
    mock_db.scalar.return_value = None  # No existing slug collision

    response = await async_client.post(
        f"{settings.api_v1_prefix}/admin/categories",
        json={
            "name": "Accessories & Bags",
            "description": "Bags, belts, and jewelry.",
            "display_order": 3,
        },
    )
    app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Accessories & Bags"
    assert data["slug"] == "accessories-bags"


@pytest.mark.asyncio
async def test_admin_create_product(
    async_client: AsyncClient, mock_db: AsyncMock, admin_user: User
) -> None:
    """Verify POST /api/v1/admin/products creates product with nested variants & pre-order."""

    async def _override_user() -> User:
        return admin_user

    app.dependency_overrides[get_current_user] = _override_user
    mock_db.scalar.return_value = None  # No slug collision

    deadline = (datetime.now(UTC) + timedelta(days=5)).isoformat()
    dispatch = (datetime.now(UTC) + timedelta(days=12)).isoformat()

    created_prod = Product(
        id=uuid.uuid4(),
        name="Ruffle Cocktail Dress",
        slug="ruffle-cocktail-dress",
        description="Feminine cocktail dress.",
        price=Decimal("290.00"),
        availability_status=ProductAvailability.PREORDER,
        is_featured=True,
        fit="Fitted bodice",
        fabric="Crepe",
        care="Dry clean",
        tags=["Cocktail"],
        offers=[],
        variants=[],
        images=[],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = created_prod
    mock_db.execute.return_value = mock_result

    response = await async_client.post(
        f"{settings.api_v1_prefix}/admin/products",
        json={
            "name": "Ruffle Cocktail Dress",
            "description": "Feminine cocktail dress.",
            "price": "290.00",
            "availability_status": "preorder",
            "is_featured": True,
            "details": {
                "fit": "Fitted bodice",
                "fabric": "Crepe",
                "care": "Dry clean",
            },
            "variants": [
                {
                    "sku": "DRS-RUF-RED-S",
                    "size": "S",
                    "color": "Red",
                    "color_hex": "#FF0000",
                    "stock_quantity": 0,
                }
            ],
            "images": [
                {
                    "url": "https://example.com/dress.jpg",
                    "alt_text": "Cocktail dress",
                    "is_primary": True,
                }
            ],
            "preorder_campaign": {
                "order_deadline": deadline,
                "expected_delivery_date": dispatch,
                "max_order_limit": 30,
            },
        },
    )
    app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Ruffle Cocktail Dress"
    assert data["price"] == "290.00"


@pytest.mark.asyncio
async def test_admin_delete_product_forbidden_for_staff(
    async_client: AsyncClient, staff_user: User
) -> None:
    """Verify DELETE /api/v1/admin/products/{id} rejects staff with 403 Forbidden."""
    test_id = uuid.uuid4()

    async def _override_staff() -> User:
        return staff_user

    app.dependency_overrides[get_current_user] = _override_staff

    response = await async_client.delete(
        f"{settings.api_v1_prefix}/admin/products/{test_id}"
    )
    app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 403
    assert "administrator access required" in response.json()["detail"].lower()
