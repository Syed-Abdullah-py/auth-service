from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool
from app.core.config import settings
from app.db.base import Base  # noqa: F401 — Alembic needs this

async_engine = create_async_engine(
    settings.ASYNC_DATABASE_URL,
    poolclass=NullPool,  # Required for Supabase session pooler
    echo=settings.ENVIRONMENT == "development",
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,  # Critical: Prevents lazy load errors after commit
)