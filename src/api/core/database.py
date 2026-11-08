import asyncio
import logging
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from api.core.config import settings

logger = logging.getLogger("api.database")

engine: AsyncEngine = create_async_engine(
    settings.db.url,
    echo=settings.debug,
    pool_size=settings.db.pool_size,
    max_overflow=settings.db.max_overflow,
    pool_timeout=settings.db.pool_timeout,
    pool_pre_ping=settings.db.pool_pre_ping,
    connect_args={
        "command_timeout": settings.db.command_timeout,
        "timeout": settings.db.connect_timeout,
    },
)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that yields an active async database session with auto rollback on error."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_database_health() -> bool:
    """Performs a quick SELECT 1 query to verify database connection with timeout."""
    try:
        async with asyncio.timeout(2.0):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning(f"Database health check failed: {exc}")
        return False


async def ensure_database_exists() -> bool:
    """Connects to the default postgres maintenance database and creates target DB if missing."""
    url = make_url(settings.db.url)
    db_name = url.database

    if not db_name or db_name == "postgres":
        return True

    # Connect to the default 'postgres' maintenance database to check/create target DB
    maintenance_url = url.set(database="postgres")
    maintenance_engine = create_async_engine(
        maintenance_url,
        isolation_level="AUTOCOMMIT",
        connect_args={
            "command_timeout": settings.db.command_timeout,
            "timeout": settings.db.connect_timeout,
        },
    )

    try:
        async with asyncio.timeout(3.0):
            async with maintenance_engine.connect() as conn:
                exists = await conn.scalar(
                    text("SELECT 1 FROM pg_database WHERE datname = :name"),
                    {"name": db_name},
                )
                if not exists:
                    logger.info(f"Database '{db_name}' not found. Creating database...")
                    await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
                    logger.info(f"Database '{db_name}' successfully created.")
        return True
    except Exception as exc:
        logger.warning(
            f"Could not verify or auto-create database '{db_name}': {exc}. "
            "Ensure PostgreSQL is running or create the database manually."
        )
        return False
    finally:
        await maintenance_engine.dispose()


async def init_db() -> None:
    """Initializes the database: ensures DB exists and creates all defined ORM tables."""
    created = await ensure_database_exists()
    if created:
        try:
            from api.models.base import Base

            async with asyncio.timeout(5.0):
                async with engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables verified/created successfully.")
        except Exception as exc:
            logger.warning(f"Table initialization skipped or failed: {exc}")
