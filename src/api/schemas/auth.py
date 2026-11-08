import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from api.models.user import UserRole


class UserResponse(BaseModel):
    """Public user schema returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None


class UserCreate(BaseModel):
    """Schema for creating a new user or administrator."""

    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=2)
    role: UserRole = UserRole.ADMIN


class LoginRequest(BaseModel):
    """JSON credentials payload for login."""

    email: EmailStr
    password: str


class Token(BaseModel):
    """OAuth2 / JWT access & refresh token pair."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenRefreshRequest(BaseModel):
    """Payload to request a new access token using a refresh token."""

    refresh_token: str
