from typing import AsyncGenerator, Optional
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import SessionLocal, AsyncSessionLocal

# Database session manager
class DatabaseSessionManager:
    """Singleton manager for async database sessions"""

    _instance: Optional["DatabaseSessionManager"] = None
    _session: Optional[AsyncSession] = None

    def __new__(cls) -> "DatabaseSessionManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def get_session(self) -> AsyncSession:
        """Get or create the singleton async session"""
        if self._session is None or not self._session.is_active:
            self._session = AsyncSessionLocal()
        return self._session

    async def close(self) -> None:
        """Close the singleton session"""
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def commit(self) -> None:
        """Commit the current session"""
        if self._session is not None:
            await self._session.commit()

    async def rollback(self) -> None:
        """Rollback the current session"""
        if self._session is not None:
            await self._session.rollback()



# Singleton instance
db_manager = DatabaseSessionManager()


def get_db():
    """FastAPI dependency for sync database sessions (backward compatibility)"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """async database sessions (uses singleton)"""
    session = await db_manager.get_session()
    try:
        yield session
    except Exception:
        await db_manager.rollback()
        raise


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager for database sessions (creates new session per call).

    Each call creates a fresh session to avoid conflicts in concurrent operations.
    """
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
