import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from httpx import AsyncClient

from api.core.config import settings
from api.core.database import get_db_session
from api.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_admin,
    get_current_user,
    hash_password,
    verify_password,
)
from api.main import app
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


def test_password_hashing() -> None:
    """Verify password hashing generates verifiable hashes and rejects mismatches."""
    password = "SuperSecretPassword123!"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_jwt_tokens_generation_and_decoding() -> None:
    """Verify generation, claim structure, and decoding of access and refresh tokens."""
    user_id = uuid.uuid4()
    access_token = create_access_token(
        subject=user_id, role="admin", expires_delta=timedelta(minutes=15)
    )
    refresh_token = create_refresh_token(
        subject=user_id, expires_delta=timedelta(days=1)
    )

    access_payload = decode_token(access_token)
    assert access_payload["sub"] == str(user_id)
    assert access_payload["role"] == "admin"
    assert access_payload["type"] == "access"

    refresh_payload = decode_token(refresh_token)
    assert refresh_payload["sub"] == str(user_id)
    assert refresh_payload["type"] == "refresh"


def test_expired_token_raises_401() -> None:
    """Verify that expired tokens raise a 401 HTTPException."""
    user_id = uuid.uuid4()
    expired_token = create_access_token(
        subject=user_id, role="admin", expires_delta=timedelta(seconds=-10)
    )
    with pytest.raises(HTTPException) as exc:
        decode_token(expired_token)
    assert exc.value.status_code == 401
    assert "expired" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_get_current_admin_authorization() -> None:
    """Verify get_current_admin allows admins and rejects non-admin roles with 403."""
    admin_user = User(
        id=uuid.uuid4(),
        email="admin@cynshub.com",
        hashed_password="hash",
        full_name="Admin User",
        role=UserRole.ADMIN,
        is_active=True,
    )
    staff_user = User(
        id=uuid.uuid4(),
        email="staff@cynshub.com",
        hashed_password="hash",
        full_name="Staff User",
        role=UserRole.STAFF,
        is_active=True,
    )

    # Admin should succeed
    admin_result = await get_current_admin(current_user=admin_user)
    assert admin_result == admin_user

    # Staff should fail with 403 Forbidden
    with pytest.raises(HTTPException) as exc:
        await get_current_admin(current_user=staff_user)
    assert exc.value.status_code == 403
    assert "Administrator access required" in exc.value.detail


@pytest.mark.asyncio
async def test_get_current_user_deactivated(mock_db: AsyncMock) -> None:
    """Verify get_current_user raises 403 when user account is deactivated."""
    user_id = uuid.uuid4()
    access_token = create_access_token(subject=user_id, role="admin")

    deactivated_user = User(
        id=user_id,
        email="inactive@cynshub.com",
        hashed_password="hash",
        full_name="Inactive User",
        role=UserRole.ADMIN,
        is_active=False,
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = deactivated_user
    mock_db.execute.return_value = mock_result

    with pytest.raises(HTTPException) as exc:
        await get_current_user(token=access_token, db=mock_db)
    assert exc.value.status_code == 403
    assert "deactivated" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_login_success(async_client: AsyncClient, mock_db: AsyncMock) -> None:
    """Verify successful login returns valid JWT tokens."""
    test_user_id = uuid.uuid4()
    mock_user = User(
        id=test_user_id,
        email="owner@cynshub.com",
        hashed_password=hash_password("adminSecret123"),
        full_name="Cynthia Owner",
        role=UserRole.ADMIN,
        is_active=True,
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_user
    mock_db.execute.return_value = mock_result

    response = await async_client.post(
        f"{settings.api_v1_prefix}/auth/login",
        json={"email": "owner@cynshub.com", "password": "adminSecret123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == settings.access_token_expire_minutes * 60


@pytest.mark.asyncio
async def test_login_invalid_password(
    async_client: AsyncClient, mock_db: AsyncMock
) -> None:
    """Verify login with incorrect password returns 401."""
    mock_user = User(
        id=uuid.uuid4(),
        email="owner@cynshub.com",
        hashed_password=hash_password("adminSecret123"),
        full_name="Cynthia Owner",
        role=UserRole.ADMIN,
        is_active=True,
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_user
    mock_db.execute.return_value = mock_result

    response = await async_client.post(
        f"{settings.api_v1_prefix}/auth/login",
        json={"email": "owner@cynshub.com", "password": "WrongPassword"},
    )
    assert response.status_code == 401
    assert "incorrect email or password" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_login_deactivated_user(
    async_client: AsyncClient, mock_db: AsyncMock
) -> None:
    """Verify login for deactivated user returns 403."""
    mock_user = User(
        id=uuid.uuid4(),
        email="deactivated@cynshub.com",
        hashed_password=hash_password("adminSecret123"),
        full_name="Former Staff",
        role=UserRole.STAFF,
        is_active=False,
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_user
    mock_db.execute.return_value = mock_result

    response = await async_client.post(
        f"{settings.api_v1_prefix}/auth/login",
        json={
            "email": "deactivated@cynshub.com",
            "password": "adminSecret123",
        },
    )
    assert response.status_code == 403
    assert "deactivated" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_refresh_token_success(
    async_client: AsyncClient, mock_db: AsyncMock
) -> None:
    """Verify token refresh generates a new access token and rotated refresh token."""
    user_id = uuid.uuid4()
    refresh_token = create_refresh_token(subject=user_id)

    mock_user = User(
        id=user_id,
        email="owner@cynshub.com",
        hashed_password="hash",
        full_name="Cynthia Owner",
        role=UserRole.ADMIN,
        is_active=True,
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_user
    mock_db.execute.return_value = mock_result

    response = await async_client.post(
        f"{settings.api_v1_prefix}/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_get_current_user_profile(
    async_client: AsyncClient, mock_db: AsyncMock
) -> None:
    """Verify GET /auth/me returns profile for valid access token."""
    user_id = uuid.uuid4()
    access_token = create_access_token(subject=user_id, role="admin")

    mock_user = User(
        id=user_id,
        email="owner@cynshub.com",
        hashed_password="hash",
        full_name="Cynthia Owner",
        role=UserRole.ADMIN,
        is_active=True,
        created_at=datetime.now(UTC),
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_user
    mock_db.execute.return_value = mock_result

    response = await async_client.get(
        f"{settings.api_v1_prefix}/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "owner@cynshub.com"
    assert data["role"] == "admin"
    assert data["full_name"] == "Cynthia Owner"


@pytest.mark.asyncio
async def test_setup_initial_admin(
    async_client: AsyncClient, mock_db: AsyncMock
) -> None:
    """Verify setup_initial_admin succeeds when 0 users exist and fails if users exist."""
    mock_db.scalar.return_value = 0  # 0 existing users

    response = await async_client.post(
        f"{settings.api_v1_prefix}/auth/setup-initial-admin",
        json={
            "email": "firstadmin@cynshub.com",
            "password": "SecurePassword123!",
            "full_name": "First Admin",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "firstadmin@cynshub.com"
    assert data["role"] == "admin"

    # Second attempt: users already exist
    mock_db.scalar.return_value = 1
    response = await async_client.post(
        f"{settings.api_v1_prefix}/auth/setup-initial-admin",
        json={
            "email": "secondadmin@cynshub.com",
            "password": "SecurePassword123!",
            "full_name": "Second Admin",
        },
    )
    assert response.status_code == 400
    assert "disabled because users already exist" in response.json()["detail"]
