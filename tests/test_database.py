from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from api.core.database import (
    check_database_health,
    ensure_database_exists,
    get_db_session,
    init_db,
)
from api.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DummyItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "dummy_items"

    name: Mapped[str] = mapped_column(String(50))


def test_base_model_mixins() -> None:
    """Verify Base and Mixins create expected table columns."""
    assert "dummy_items" in Base.metadata.tables
    table = Base.metadata.tables["dummy_items"]
    assert "id" in table.columns
    assert "created_at" in table.columns
    assert "updated_at" in table.columns
    assert "name" in table.columns
    assert table.columns["id"].primary_key is True


@pytest.mark.asyncio
async def test_get_db_session_lifecycle() -> None:
    """Ensure get_db_session yields an active session and commits."""
    mock_session = AsyncMock()
    mock_maker = MagicMock()
    mock_maker.return_value.__aenter__.return_value = mock_session

    with patch("api.core.database.AsyncSessionLocal", mock_maker):
        async for session in get_db_session():
            assert session == mock_session
        mock_session.commit.assert_awaited_once()
        mock_session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_database_health_handles_disconnect() -> None:
    """Verify check_database_health returns False when DB is unreachable."""
    mock_engine = MagicMock()
    mock_engine.connect.side_effect = Exception("DB Unreachable")
    with patch("api.core.database.engine", mock_engine):
        healthy = await check_database_health()
        assert healthy is False


@pytest.mark.asyncio
async def test_check_database_health_success() -> None:
    """Verify check_database_health returns True on successful ping."""
    mock_conn = AsyncMock()
    mock_engine = MagicMock()
    mock_engine.connect.return_value.__aenter__.return_value = mock_conn

    with patch("api.core.database.engine", mock_engine):
        healthy = await check_database_health()
        assert healthy is True


@pytest.mark.asyncio
async def test_ensure_database_exists_already_present() -> None:
    """Verify ensure_database_exists does not attempt creation if DB is already present."""
    mock_conn = AsyncMock()
    mock_conn.scalar.return_value = 1
    mock_engine = MagicMock()
    mock_engine.dispose = AsyncMock()
    mock_engine.connect.return_value.__aenter__.return_value = mock_conn

    with patch("api.core.database.create_async_engine", return_value=mock_engine):
        res = await ensure_database_exists()
        assert res is True
        mock_conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_database_exists_creates_db() -> None:
    """Verify ensure_database_exists executes CREATE DATABASE if DB is missing."""
    mock_conn = AsyncMock()
    mock_conn.scalar.return_value = None
    mock_engine = MagicMock()
    mock_engine.dispose = AsyncMock()
    mock_engine.connect.return_value.__aenter__.return_value = mock_conn

    with patch("api.core.database.create_async_engine", return_value=mock_engine):
        res = await ensure_database_exists()
        assert res is True
        mock_conn.execute.assert_called_once()
        query = str(mock_conn.execute.call_args[0][0])
        assert "CREATE DATABASE" in query


@pytest.mark.asyncio
async def test_init_db_runs_create_all() -> None:
    """Verify init_db executes metadata.create_all on engine."""
    with (
        patch("api.core.database.ensure_database_exists", return_value=True),
        patch("api.core.database.engine") as mock_engine,
    ):
        mock_conn = AsyncMock()
        mock_engine.begin.return_value.__aenter__.return_value = mock_conn
        await init_db()
        mock_conn.run_sync.assert_called_once()
