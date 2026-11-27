import tomllib
from functools import lru_cache
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings

PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]


def get_project_version() -> str:
    """Reads version from pyproject.toml (dev) or package metadata (installed)."""
    pyproject_path: Path = PROJECT_ROOT / "pyproject.toml"

    if pyproject_path.is_file():
        try:
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
                if ver := data.get("project", {}).get("version"):
                    return ver
        except Exception:
            pass

    try:
        return pkg_version("api")
    except PackageNotFoundError:
        return "0.1.0"


class DatabaseConfig(BaseSettings):
    """Database connection and connection pool configuration."""

    url: str = Field(
        default="postgresql+asyncpg://postgres:francis@localhost:5432/cyns_hub",
        validation_alias=AliasChoices("DATABASE_URL", "database_url"),
        description="Full asyncpg database connection string",
    )
    pool_size: int = Field(
        default=5,
        validation_alias=AliasChoices("DATABASE_POOL_SIZE", "database_pool_size"),
    )
    max_overflow: int = Field(
        default=10,
        validation_alias=AliasChoices("DATABASE_MAX_OVERFLOW", "database_max_overflow"),
    )
    pool_timeout: float = Field(
        default=30.0,
        validation_alias=AliasChoices("DATABASE_POOL_TIMEOUT", "database_pool_timeout"),
    )
    pool_pre_ping: bool = True
    command_timeout: int = 5
    connect_timeout: int = 5


class PaystackConfig(BaseSettings):
    """Paystack payment gateway configuration."""

    secret_key: str = Field(
        default="sk_test_mock_secret_key_for_dev",
        validation_alias=AliasChoices("PAYSTACK_SECRET_KEY", "paystack_secret_key"),
        description="Paystack secret API key",
    )
    public_key: str = Field(
        default="pk_test_mock_public_key_for_dev",
        validation_alias=AliasChoices("PAYSTACK_PUBLIC_KEY", "paystack_public_key"),
        description="Paystack public API key",
    )
    base_url: str = Field(
        default="https://api.paystack.co",
        validation_alias=AliasChoices("PAYSTACK_BASE_URL", "paystack_base_url"),
        description="Paystack base API URL",
    )
    callback_url: str = Field(
        default="http://localhost:3000/checkout/callback",
        validation_alias=AliasChoices("PAYSTACK_CALLBACK_URL", "paystack_callback_url"),
        description="Default redirect URL after payment completion",
    )


class NotificationConfig(BaseSettings):
    """SMS and WhatsApp messaging configuration."""

    enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("NOTIFICATIONS_ENABLED", "notifications_enabled"),
        description="Whether outbound alerts are globally enabled",
    )
    arkesel_api_key: str = Field(
        default="mock_arkesel_api_key",
        validation_alias=AliasChoices("ARKESEL_API_KEY", "arkesel_api_key"),
        description="Arkesel SMS API v2 key",
    )
    arkesel_sender_id: str = Field(
        default="CynsHub",
        validation_alias=AliasChoices("ARKESEL_SENDER_ID", "arkesel_sender_id"),
        description="Approved sender ID on Arkesel dashboard",
    )
    arkesel_sms_url: str = Field(
        default="https://sms.arkesel.com/api/v2/sms/send",
        validation_alias=AliasChoices("ARKESEL_SMS_URL", "arkesel_sms_url"),
        description="Arkesel SMS endpoint",
    )

    whatsapp_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("WHATSAPP_ENABLED", "whatsapp_enabled"),
        description="Whether WhatsApp alerts are active",
    )
    whatsapp_access_token: str = Field(
        default="mock_whatsapp_token",
        validation_alias=AliasChoices("WHATSAPP_ACCESS_TOKEN", "whatsapp_access_token"),
        description="Meta / Arkesel WhatsApp Cloud API access token",
    )
    whatsapp_phone_number_id: str = Field(
        default="mock_phone_number_id",
        validation_alias=AliasChoices(
            "WHATSAPP_PHONE_NUMBER_ID", "whatsapp_phone_number_id"
        ),
        description="Meta WhatsApp business phone number ID",
    )
    whatsapp_api_url: str = Field(
        default="https://graph.facebook.com/v17.0",
        validation_alias=AliasChoices("WHATSAPP_API_URL", "whatsapp_api_url"),
        description="Base WhatsApp Graph API URL",
    )

    admin_alert_phone: str = Field(
        default="+233240000000",
        validation_alias=AliasChoices("ADMIN_ALERT_PHONE", "admin_alert_phone"),
        description="Business owner phone number for admin notifications",
    )
    storefront_url: str = Field(
        default="http://localhost:3000",
        validation_alias=AliasChoices("STOREFRONT_URL", "storefront_url"),
        description="Public storefront URL used in tracking links",
    )


class Config(BaseSettings):
    """Global application settings."""

    version: str = Field(default_factory=get_project_version)
    api_v1_prefix: str = "/api/v1"
    env: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    json_logs: bool = False

    # Separated Database Sub-configuration
    db: DatabaseConfig = Field(default_factory=DatabaseConfig)

    # Paystack Payment Gateway
    paystack: PaystackConfig = Field(default_factory=PaystackConfig)

    # Notifications & Alerts
    notifications: NotificationConfig = Field(default_factory=NotificationConfig)

    # Authentication & Security
    jwt_secret_key: str = "cyns-hub-super-secret-key-change-in-production-min-32-chars"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7


@lru_cache
def get_settings() -> Config:
    return Config()


settings = get_settings()
