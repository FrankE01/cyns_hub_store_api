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


class LoginCredentials(BaseModel):
    """Normalized credentials extracted from JSON or OAuth2 form payload."""

    email: str
    password: str


LOGIN_OPENAPI_EXTRA = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "email": {
                            "type": "string",
                            "format": "email",
                            "example": "admin@cynshub.com",
                        },
                        "password": {
                            "type": "string",
                            "format": "password",
                            "example": "adminSecret123",
                        },
                    },
                    "required": ["email", "password"],
                }
            },
            "application/x-www-form-urlencoded": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "grant_type": {
                            "type": "string",
                            "example": "password",
                        },
                        "username": {
                            "type": "string",
                            "description": "User email address",
                            "example": "admin@cynshub.com",
                        },
                        "password": {
                            "type": "string",
                            "format": "password",
                            "example": "adminSecret123",
                        },
                        "scope": {"type": "string", "default": ""},
                        "client_id": {"type": "string", "nullable": True},
                        "client_secret": {"type": "string", "nullable": True},
                    },
                    "required": ["username", "password"],
                }
            },
        },
    }
}
