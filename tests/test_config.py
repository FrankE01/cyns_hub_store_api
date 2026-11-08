from api.core.config import Config, get_project_version, get_settings


def test_get_settings() -> None:
    """Verify settings singleton loads expected defaults."""
    settings = get_settings()
    assert isinstance(settings, Config)
    assert settings.api_v1_prefix == "/api/v1"
    assert bool(settings.version)


def test_get_project_version() -> None:
    """Verify project version is read from pyproject.toml."""
    version = get_project_version()
    assert version == "0.1.0"
