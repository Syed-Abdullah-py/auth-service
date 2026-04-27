# app/core/config.py
from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
import os
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # JWT
    SECRET_KEY: str = os.getenv("SECRET_KEY")
    ALGORITHM: str = os.getenv("ALGORITHM")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES")

    # DB mode switch — flip this one flag in .env to go local
    USE_LOCAL_DB: bool = False

    # Local Postgres (used when USE_LOCAL_DB=true)
    LOCAL_DB_HOST: str = "localhost"
    LOCAL_DB_PORT: str = "5432"
    LOCAL_DB_USER: str = "postgres"
    LOCAL_DB_PASSWORD: str = "postgres"
    LOCAL_DB_NAME: str = "neuroscan"

    # Supabase DB (used when USE_LOCAL_DB=false)
    SUPABASE_DB_USER: Optional[str] = None
    SUPABASE_DB_PASSWORD: Optional[str] = None
    SUPABASE_DB_HOST: Optional[str] = None
    SUPABASE_DB_PORT: Optional[str] = None
    SUPABASE_DB_NAME: Optional[str] = None
    SUPABASE_DB_PREPARE_STATEMENTS: bool = False

    # Storage
    SUPABASE_URL: Optional[str] = None
    SUPABASE_SERVICE_KEY: Optional[str] = None
    SUPABASE_STORAGE_BUCKET: Optional[str] = None

    # App
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    CORS_ORIGINS: list[str] = os.getenv("CORS_ORIGINS")

    # OAuth
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")

    @property
    def DATABASE_URL(self) -> str:
        """Sync URL — Alembic only."""
        if self.USE_LOCAL_DB:
            return (
                f"postgresql+psycopg2://{self.LOCAL_DB_USER}:{self.LOCAL_DB_PASSWORD}"
                f"@{self.LOCAL_DB_HOST}:{self.LOCAL_DB_PORT}/{self.LOCAL_DB_NAME}"
            )
        return (
            f"postgresql+psycopg2://{self.SUPABASE_DB_USER}:{self.SUPABASE_DB_PASSWORD}"
            f"@{self.SUPABASE_DB_HOST}:{self.SUPABASE_DB_PORT}/{self.SUPABASE_DB_NAME}"
            "?sslmode=require"
        )

    @property
    def ASYNC_DATABASE_URL(self) -> str:
        """Async URL — used by the FastAPI app."""
        if self.USE_LOCAL_DB:
            return (
                f"postgresql+asyncpg://{self.LOCAL_DB_USER}:{self.LOCAL_DB_PASSWORD}"
                f"@{self.LOCAL_DB_HOST}:{self.LOCAL_DB_PORT}/{self.LOCAL_DB_NAME}"
            )
        return (
            f"postgresql+asyncpg://{self.SUPABASE_DB_USER}:{self.SUPABASE_DB_PASSWORD}"
            f"@{self.SUPABASE_DB_HOST}:{self.SUPABASE_DB_PORT}/{self.SUPABASE_DB_NAME}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
