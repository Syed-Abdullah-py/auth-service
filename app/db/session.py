# app/db/session.py
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from app.core.config import settings
from app.db.base import Base  # noqa: F401 - Alembic needs this

# Supabase requires SSL + disabled prepared-statement cache (PgBouncer limitation).
# Local Postgres needs neither.
_connect_args: dict = (
    {}
    if settings.USE_LOCAL_DB
    else {
        "ssl": "require",
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
    }
)

async_engine = create_async_engine(
    settings.ASYNC_DATABASE_URL,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    connect_args=_connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)
