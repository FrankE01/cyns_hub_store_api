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

    # Authentication & Security
    jwt_secret_key: str = "cyns-hub-super-secret-key-change-in-production-min-32-chars"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7


@lru_cache
def get_settings() -> Config:
    return Config()


settings = get_settings()
