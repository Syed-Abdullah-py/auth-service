from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Supabase credentials
DB_USER = os.getenv("SUPABASE_DB_USER")
DB_PASSWORD = os.getenv("SUPABASE_DB_PASSWORD")
DB_HOST = os.getenv("SUPABASE_DB_HOST")
DB_PORT = os.getenv("SUPABASE_DB_PORT", "5432")
DB_NAME = os.getenv("SUPABASE_DB_NAME", "postgres")

# Database URL
# Database URL
if DB_USER and DB_PASSWORD and DB_HOST:
    DATABASE_URL = (
        f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}?sslmode=require"
    )
    ASYNC_DATABASE_URL = (
        f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}?ssl=require"
    )
    connect_args = {}
else:
    # Fallback to SQLite
    DATABASE_URL = "sqlite:///./test.db"
    ASYNC_DATABASE_URL = "sqlite+aiosqlite:///./test.db"
    connect_args = {"check_same_thread": False}

# Base for models
Base = declarative_base()

# Database engine (Sync)
engine = create_engine(
    DATABASE_URL,
    poolclass=NullPool,
    connect_args=connect_args if "sqlite" in DATABASE_URL else {},
)

# Database engine (Async)
async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    poolclass=NullPool,
    connect_args=connect_args if "sqlite" in ASYNC_DATABASE_URL else {},
)

# Session Local (Sync)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Session Local (Async)
AsyncSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# Testing for python individual module
if __name__ == "__main__":
    try:
        with engine.connect() as connection:
            print("✅ Supabase connection successful!")
    except Exception as e:
        print(f"❌ Failed to connect: {e}")
