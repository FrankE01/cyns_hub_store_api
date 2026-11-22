import hashlib
import hmac
import json
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from api.core.config import settings
from api.core.database import get_db_session
from api.core.security import get_current_user
from api.main import app
from api.models.order import (
    FulfillmentStatus,
    Order,
    PaymentMethod,
    PaymentStatus,
)
from api.models.payment import Payment
from api.models.user import User, UserRole
from api.services.paystack import PaystackService


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
    """Fixture for an unpaid standard order."""
    return Order(
        id=uuid.uuid4(),
        reference="CYN-20261122-A1B2",
        customer_name="Akua Mensah",
        customer_phone="+233241234567",
        customer_email="akua@example.com",
        delivery_region="Greater Accra",
        delivery_address="12 Boundary Road, East Legon",
        subtotal=Decimal("300.00"),
        delivery_fee=Decimal("30.00"),
        total=Decimal("330.00"),
        payment_method=PaymentMethod.MOMO_PAYSTACK,
        payment_status=PaymentStatus.PENDING,
        fulfillment_status=FulfillmentStatus.AWAITING_PAYMENT,
        is_pre_order=False,
    )


@pytest.fixture
def sample_preorder() -> Order:
    """Fixture for an unpaid pre-order."""
    return Order(
        id=uuid.uuid4(),
        reference="CYN-20261122-PRE9",
        customer_name="Kofi Annan",
        customer_phone="+233501234567",
        customer_email="kofi@example.com",
        delivery_region="Ashanti",
        delivery_address="Kumasi Central",
        subtotal=Decimal("600.00"),
        delivery_fee=Decimal("0.00"),
        total=Decimal("600.00"),
        payment_method=PaymentMethod.MOMO_PAYSTACK,
        payment_status=PaymentStatus.PENDING,
        fulfillment_status=FulfillmentStatus.AWAITING_PAYMENT,
        is_pre_order=True,
    )


def compute_test_signature(
    body: bytes, secret: str = "sk_test_mock_secret_key_for_dev"
) -> str:
    """Computes HMAC SHA512 signature matching Paystack webhook contract."""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha512).hexdigest()


# ---------------------------------------------------------------------------
# Unit Tests: Paystack Client & Signature Verification
# ---------------------------------------------------------------------------


def test_paystack_webhook_signature_verification() -> None:
    """Verify HMAC SHA512 signature computation against Paystack specification."""
    secret = "test_secret_key_123"
    body = b'{"event":"charge.success","data":{"reference":"REF-123"}}'
    correct_sig = compute_test_signature(body, secret)

    assert PaystackService.verify_webhook_signature(body, correct_sig, secret) is True
    assert (
        PaystackService.verify_webhook_signature(body, "invalid_sig", secret) is False
    )
    assert PaystackService.verify_webhook_signature(body, None, secret) is False


@pytest.mark.asyncio
async def test_paystack_service_initialize_mocked() -> None:
    """Test PaystackService.initialize_transaction payload structure and response parsing."""
    service = PaystackService(
        secret_key="sk_test_mock", base_url="https://api.paystack.mock"
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": True,
        "message": "Authorization URL created",
        "data": {
            "authorization_url": "https://checkout.paystack.com/access_code_123",
            "access_code": "access_code_123",
            "reference": "REF-ABC-1",
        },
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        data = await service.initialize_transaction(
            email="test@cynshub.com",
            amount_pesewas=33000,
            reference="REF-ABC-1",
        )
        assert (
            data["authorization_url"] == "https://checkout.paystack.com/access_code_123"
        )
        assert data["access_code"] == "access_code_123"


# ---------------------------------------------------------------------------
# Integration Tests: Storefront Payment Endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initialize_payment_endpoint(
    mock_db: AsyncMock,
    sample_order: Order,
) -> None:
    """Verify POST /api/v1/payments/initialize initiates Paystack session."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sample_order
    mock_db.execute.return_value = mock_result

    with patch(
        "api.services.paystack.paystack_service.initialize_transaction",
        new_callable=AsyncMock,
    ) as mock_init:
        mock_init.return_value = {
            "authorization_url": "https://checkout.paystack.com/xyz123",
            "access_code": "xyz123",
            "reference": "PAY-CYN-20261122-A1B2-MOCK",
        }

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            response = await ac.post(
                f"{settings.api_v1_prefix}/payments/initialize",
                json={"order_reference": sample_order.reference},
            )

        assert response.status_code == 201
        res = response.json()
        assert res["order_reference"] == sample_order.reference
        assert res["authorization_url"] == "https://checkout.paystack.com/xyz123"
        assert res["access_code"] == "xyz123"
        assert float(res["amount"]) == 330.0
        mock_db.add.assert_called()


@pytest.mark.asyncio
async def test_initialize_payment_already_paid_fails(
    mock_db: AsyncMock,
    sample_order: Order,
) -> None:
    """Verify initializing payment for an already paid order raises 400."""
    sample_order.payment_status = PaymentStatus.PAID
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sample_order
    mock_db.execute.return_value = mock_result

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        response = await ac.post(
            f"{settings.api_v1_prefix}/payments/initialize",
            json={"order_reference": sample_order.reference},
        )

    assert response.status_code == 400
    assert "already been paid" in response.json()["detail"]


@pytest.mark.asyncio
async def test_verify_payment_endpoint_updates_order_state(
    mock_db: AsyncMock,
    sample_order: Order,
) -> None:
    """Verify GET /api/v1/payments/verify/{reference} transitions in-stock order to PROCESSING."""
    payment = Payment(
        id=uuid.uuid4(),
        order_id=sample_order.id,
        amount=sample_order.total,
        currency="GHS",
        payment_method=PaymentMethod.MOMO_PAYSTACK,
        payment_status=PaymentStatus.PENDING,
        provider="paystack",
        provider_reference="PAY-CYN-20261122-A1B2-REF",
        created_at=datetime.now(UTC),
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = payment
    mock_db.execute.return_value = mock_result
    mock_db.get.return_value = sample_order

    with patch(
        "api.services.paystack.paystack_service.verify_transaction",
        new_callable=AsyncMock,
    ) as mock_verify:
        mock_verify.return_value = {
            "status": "success",
            "reference": payment.provider_reference,
            "amount": 33000,
            "currency": "GHS",
        }

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            response = await ac.get(
                f"{settings.api_v1_prefix}/payments/verify/{payment.provider_reference}",
            )

        assert response.status_code == 200
        res = response.json()
        assert res["payment_status"] == PaymentStatus.PAID
        assert sample_order.payment_status == PaymentStatus.PAID
        assert sample_order.fulfillment_status == FulfillmentStatus.PROCESSING


# ---------------------------------------------------------------------------
# Integration Tests: Paystack Webhook Handler & Idempotency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_paystack_webhook_charge_success_preorder(
    mock_db: AsyncMock,
    sample_preorder: Order,
) -> None:
    """Verify Paystack webhook transitions pre-order to AWAITING_STOCK with valid HMAC signature."""
    payment = Payment(
        id=uuid.uuid4(),
        order_id=sample_preorder.id,
        amount=sample_preorder.total,
        currency="GHS",
        payment_method=PaymentMethod.MOMO_PAYSTACK,
        payment_status=PaymentStatus.PENDING,
        provider="paystack",
        provider_reference="PAY-PRE-REF-123",
        created_at=datetime.now(UTC),
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = payment
    mock_db.execute.return_value = mock_result
    mock_db.get.return_value = sample_preorder

    payload = {
        "event": "charge.success",
        "data": {
            "reference": "PAY-PRE-REF-123",
            "amount": 60000,
            "currency": "GHS",
            "status": "success",
        },
    }
    payload_bytes = json.dumps(payload).encode("utf-8")
    sig = compute_test_signature(payload_bytes, settings.paystack.secret_key)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        response = await ac.post(
            f"{settings.api_v1_prefix}/payments/webhook",
            content=payload_bytes,
            headers={"x-paystack-signature": sig, "Content-Type": "application/json"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert payment.payment_status == PaymentStatus.PAID
    assert sample_preorder.payment_status == PaymentStatus.PAID
    assert sample_preorder.fulfillment_status == FulfillmentStatus.AWAITING_STOCK


@pytest.mark.asyncio
async def test_paystack_webhook_invalid_signature_rejected() -> None:
    """Verify webhook with invalid HMAC signature is rejected with 400 Bad Request."""
    payload_bytes = b'{"event":"charge.success"}'

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        response = await ac.post(
            f"{settings.api_v1_prefix}/payments/webhook",
            content=payload_bytes,
            headers={
                "x-paystack-signature": "bogus_signature",
                "Content-Type": "application/json",
            },
        )

    assert response.status_code == 400
    assert "Invalid Paystack signature" in response.json()["detail"]


@pytest.mark.asyncio
async def test_paystack_webhook_idempotency(
    mock_db: AsyncMock,
    sample_order: Order,
) -> None:
    """Verify duplicate webhook calls for an already-paid payment return cleanly without side-effects."""
    payment = Payment(
        id=uuid.uuid4(),
        order_id=sample_order.id,
        amount=sample_order.total,
        currency="GHS",
        payment_method=PaymentMethod.MOMO_PAYSTACK,
        payment_status=PaymentStatus.PAID,
        provider="paystack",
        provider_reference="PAY-IDEMPOTENT-REF",
        paid_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = payment
    mock_db.execute.return_value = mock_result

    payload = {
        "event": "charge.success",
        "data": {
            "reference": "PAY-IDEMPOTENT-REF",
            "amount": 33000,
            "currency": "GHS",
            "status": "success",
        },
    }
    payload_bytes = json.dumps(payload).encode("utf-8")
    sig = compute_test_signature(payload_bytes, settings.paystack.secret_key)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        response = await ac.post(
            f"{settings.api_v1_prefix}/payments/webhook",
            content=payload_bytes,
            headers={"x-paystack-signature": sig, "Content-Type": "application/json"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "success"


# ---------------------------------------------------------------------------
# Integration Tests: Direct Mobile Money (Customer Submit & Admin Verify)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_manual_payment_submission(
    mock_db: AsyncMock,
    sample_order: Order,
) -> None:
    """Verify customer can submit manual MoMo transaction reference."""
    mock_order_res = MagicMock()
    mock_order_res.scalar_one_or_none.return_value = sample_order

    mock_existing_res = MagicMock()
    mock_existing_res.scalar_one_or_none.return_value = None

    mock_db.execute.side_effect = [mock_order_res, mock_existing_res]

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        response = await ac.post(
            f"{settings.api_v1_prefix}/payments/manual-submit",
            json={
                "order_reference": sample_order.reference,
                "transaction_reference": "MTN-TX-987654321",
                "sender_phone": "+233241234567",
                "notes": "Sent via MTN Mobile Money",
            },
        )

    assert response.status_code == 201
    res = response.json()
    assert res["provider"] == "manual_momo"
    assert res["provider_reference"] == "MTN-TX-987654321"
    assert res["payment_status"] == PaymentStatus.PENDING


@pytest.mark.asyncio
async def test_admin_verify_manual_payment(
    mock_db: AsyncMock,
    sample_order: Order,
    admin_user: User,
) -> None:
    """Verify administrator can approve manual MoMo deposit and advance order to PROCESSING."""

    async def _override_user() -> User:
        return admin_user

    app.dependency_overrides[get_current_user] = _override_user

    try:
        payment = Payment(
            id=uuid.uuid4(),
            order_id=sample_order.id,
            amount=sample_order.total,
            currency="GHS",
            payment_method=PaymentMethod.DIRECT_MOMO,
            payment_status=PaymentStatus.PENDING,
            provider="manual_momo",
            provider_reference="MTN-TX-987654321",
            notes="Customer sent funds",
            created_at=datetime.now(UTC),
        )

        mock_db.get.side_effect = [payment, sample_order]

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            response = await ac.post(
                f"{settings.api_v1_prefix}/admin/payments/{payment.id}/verify",
                json={"notes": "Confirmed on MTN Merchant wallet"},
            )

        assert response.status_code == 200
        res = response.json()
        assert res["payment_status"] == PaymentStatus.PAID
        assert sample_order.payment_status == PaymentStatus.PAID
        assert sample_order.fulfillment_status == FulfillmentStatus.PROCESSING
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_admin_reject_manual_payment(
    mock_db: AsyncMock,
    sample_order: Order,
    admin_user: User,
) -> None:
    """Verify administrator can reject fraudulent/unverified manual payment submission."""

    async def _override_user() -> User:
        return admin_user

    app.dependency_overrides[get_current_user] = _override_user

    try:
        payment = Payment(
            id=uuid.uuid4(),
            order_id=sample_order.id,
            amount=sample_order.total,
            currency="GHS",
            payment_method=PaymentMethod.DIRECT_MOMO,
            payment_status=PaymentStatus.PENDING,
            provider="manual_momo",
            provider_reference="FAKE-TX-000",
            created_at=datetime.now(UTC),
        )

        mock_db.get.side_effect = [payment, sample_order]

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            response = await ac.post(
                f"{settings.api_v1_prefix}/admin/payments/{payment.id}/reject",
                json={"reason": "Transaction ID does not exist on telecom statement"},
            )

        assert response.status_code == 200
        res = response.json()
        assert res["payment_status"] == PaymentStatus.FAILED
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_admin_payment_endpoints_require_authentication() -> None:
    """Verify unauthorized requests to admin payment endpoints return 401."""
    payment_id = uuid.uuid4()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        response = await ac.get(f"{settings.api_v1_prefix}/admin/payments")
        assert response.status_code == 401

        verify_resp = await ac.post(
            f"{settings.api_v1_prefix}/admin/payments/{payment_id}/verify",
            json={"notes": "test"},
        )
        assert verify_resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_list_payments(
    mock_db: AsyncMock,
    sample_order: Order,
    admin_user: User,
) -> None:
    """Verify administrator can retrieve paginated payment records."""

    async def _override_user() -> User:
        return admin_user

    app.dependency_overrides[get_current_user] = _override_user

    try:
        payment = Payment(
            id=uuid.uuid4(),
            order_id=sample_order.id,
            amount=sample_order.total,
            currency="GHS",
            payment_method=PaymentMethod.MOMO_PAYSTACK,
            payment_status=PaymentStatus.PAID,
            provider="paystack",
            provider_reference="PAY-ADMIN-LIST",
            paid_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )

        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 1

        mock_items = MagicMock()
        mock_items.scalars.return_value.all.return_value = [payment]

        mock_db.execute.side_effect = [mock_count, mock_items]

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            response = await ac.get(f"{settings.api_v1_prefix}/admin/payments")

        assert response.status_code == 200
        res = response.json()
        assert res["total"] == 1
        assert len(res["items"]) == 1
        assert res["items"][0]["provider_reference"] == "PAY-ADMIN-LIST"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_admin_get_payment_by_id(
    mock_db: AsyncMock,
    sample_order: Order,
    admin_user: User,
) -> None:
    """Verify administrator can retrieve details for a specific payment."""

    async def _override_user() -> User:
        return admin_user

    app.dependency_overrides[get_current_user] = _override_user

    try:
        payment = Payment(
            id=uuid.uuid4(),
            order_id=sample_order.id,
            amount=sample_order.total,
            currency="GHS",
            payment_method=PaymentMethod.DIRECT_MOMO,
            payment_status=PaymentStatus.PENDING,
            provider="manual_momo",
            provider_reference="MTN-GET-ID",
            created_at=datetime.now(UTC),
        )

        mock_db.get.return_value = payment

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            response = await ac.get(
                f"{settings.api_v1_prefix}/admin/payments/{payment.id}",
            )

        assert response.status_code == 200
        res = response.json()
        assert res["id"] == str(payment.id)
        assert res["provider_reference"] == "MTN-GET-ID"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
