import tomllib
from functools import lru_cache
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from pathlib import Path

from pydantic import Field
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


class Config(BaseSettings):
    version: str = Field(default_factory=get_project_version)
    api_v1_prefix: str = "/api/v1"


@lru_cache
def get_settings() -> Config:
    return Config()


settings = get_settings()
