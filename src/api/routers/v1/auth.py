from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db_session
from api.core.security import extract_login_credentials, get_current_user
from api.models.user import User
from api.schemas.auth import (
    LOGIN_OPENAPI_EXTRA,
    LoginCredentials,
    Token,
    TokenRefreshRequest,
    UserCreate,
    UserResponse,
)
from api.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/login",
    response_model=Token,
    summary="Authenticate user and issue JWT tokens",
    description="Authenticates admin/staff credentials via JSON or OAuth2 form-urlencoded (Swagger 'Authorize').",
    openapi_extra=LOGIN_OPENAPI_EXTRA,
)
async def login(
    credentials: Annotated[LoginCredentials, Depends(extract_login_credentials)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Token:
    """Authenticates admin/staff credentials and returns JWT token pair."""
    return await AuthService.authenticate(db, credentials.email, credentials.password)


@router.post(
    "/token",
    response_model=Token,
    include_in_schema=False,
)
async def token_alias(
    credentials: Annotated[LoginCredentials, Depends(extract_login_credentials)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Token:
    """OAuth2 standard token endpoint alias for /login."""
    return await AuthService.authenticate(db, credentials.email, credentials.password)


@router.post("/refresh", response_model=Token)
async def refresh_token(
    payload: TokenRefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Token:
    """Refreshes an expired access token using a valid refresh token."""
    return await AuthService.refresh_access_token(db, payload.refresh_token)


@router.get("/me", response_model=UserResponse)
async def get_my_profile(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    """Returns the profile of the currently authenticated administrator/staff."""
    return UserResponse.model_validate(current_user)


@router.post(
    "/setup-initial-admin",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def setup_initial_admin(
    payload: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserResponse:
    """Bootstraps the very first admin user. Only allowed when 0 users exist."""
    admin_user = await AuthService.create_initial_admin(db, payload)
    return UserResponse.model_validate(admin_user)
