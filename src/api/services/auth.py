import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.config import settings
from api.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from api.models.user import User, UserRole
from api.schemas.auth import Token, UserCreate


class AuthService:
    """Business logic service for user authentication, token issuance, and account provisioning."""

    @staticmethod
    async def authenticate(
        db: AsyncSession,
        email: str,
        password: str,
    ) -> Token:
        """Authenticates user credentials and issues a signed JWT token pair."""
        normalized_email = email.lower().strip()
        query = select(User).where(User.email == normalized_email)
        result = await db.execute(query)
        user = result.scalar_one_or_none()

        if not user or not verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated",
            )

        user.last_login_at = datetime.now(UTC)
        await db.commit()

        access_token = create_access_token(subject=user.id, role=user.role.value)
        refresh_token = create_refresh_token(subject=user.id)

        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60,
        )

    @staticmethod
    async def refresh_access_token(
        db: AsyncSession,
        refresh_token_str: str,
    ) -> Token:
        """Validates a refresh token and generates a fresh access token with rotation."""
        token_data = decode_token(refresh_token_str)
        if token_data.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user_id_str = token_data.get("sub")
        if not user_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing user identity",
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            user_id = uuid.UUID(user_id_str)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user identity format",
                headers={"WWW-Authenticate": "Bearer"},
            ) from None

        query = select(User).where(User.id == user_id)
        result = await db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated",
            )

        new_access_token = create_access_token(subject=user.id, role=user.role.value)
        new_refresh_token = create_refresh_token(subject=user.id)

        return Token(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60,
        )

    @staticmethod
    async def create_initial_admin(
        db: AsyncSession,
        payload: UserCreate,
    ) -> User:
        """Bootstraps the very first admin user. Only allowed when 0 users exist."""
        count_query = select(func.count()).select_from(User)
        count = await db.scalar(count_query)

        if count and count > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Initial admin setup is disabled because users already exist.",
            )

        admin_user = User(
            id=uuid.uuid4(),
            email=payload.email.lower().strip(),
            hashed_password=hash_password(payload.password),
            full_name=payload.full_name.strip(),
            role=UserRole.ADMIN,
            is_active=True,
            created_at=datetime.now(UTC),
        )

        db.add(admin_user)
        await db.commit()
        await db.refresh(admin_user)

        return admin_user
