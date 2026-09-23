"""Database connection and session lifecycle management."""

import logging
from typing import AsyncGenerator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config.settings import settings
from src.database.models import Base

logger = logging.getLogger(__name__)

# Global async engine
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

# Async session factory
ASYNC_SESSION_LOCAL = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for providing an async database session."""
    async with ASYNC_SESSION_LOCAL() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database extensions and schema."""
    logger.info("Initializing database and ensuring pgvector extension is installed...")
    async with engine.begin() as conn:
        # Enable pgvector extension
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        # Create all tables defined in Base metadata
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialization completed.")


async def close_db() -> None:
    """Dispose engine connections on shutdown."""
    await engine.dispose()
    logger.info("Database connection pool closed.")
