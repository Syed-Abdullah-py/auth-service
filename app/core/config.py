# app/core/config.py
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
import os
from dotenv import load_dotenv

# Load variables from .env file
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

    # Supabase
    SUPABASE_DB_USER: str = os.getenv("SUPABASE_DB_USER")
    SUPABASE_DB_PASSWORD: str = os.getenv("SUPABASE_DB_PASSWORD")
    SUPABASE_DB_HOST: str = os.getenv("SUPABASE_DB_HOST")
    SUPABASE_DB_PORT: str = os.getenv("SUPABASE_DB_PORT")
    SUPABASE_DB_NAME: str = os.getenv("SUPABASE_DB_NAME")
    SUPABASE_DB_PREPARE_STATEMENTS: bool = os.getenv("SUPABASE_DB_PREPARE_STATEMENTS")

    # Storage
    SUPABASE_URL: str = os.getenv("SUPABASE_URL")
    SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY")
    SUPABASE_STORAGE_BUCKET: str = os.getenv("SUPABASE_STORAGE_BUCKET")

    # App
    ENVIRONMENT: str = os.getenv("ENVIRONMENT")
    CORS_ORIGINS: list[str] = os.getenv("CORS_ORIGINS")

    # OAuth
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")

    @property
    def DATABASE_URL(self) -> str:
        """Sync URL — Alembic only."""
        if self.SUPABASE_DB_HOST:
            return (
                f"postgresql+psycopg2://{self.SUPABASE_DB_USER}:{self.SUPABASE_DB_PASSWORD}"
                f"@{self.SUPABASE_DB_HOST}:{self.SUPABASE_DB_PORT}/{self.SUPABASE_DB_NAME}"
                "?sslmode=require"
            )
        return "sqlite:///./dev.db"

    @property
    def ASYNC_DATABASE_URL(self) -> str:
        """Async URL — used by the FastAPI app."""
        if self.SUPABASE_DB_HOST:
            return (
                f"postgresql+asyncpg://{self.SUPABASE_DB_USER}:{self.SUPABASE_DB_PASSWORD}"
                f"@{self.SUPABASE_DB_HOST}:{self.SUPABASE_DB_PORT}/{self.SUPABASE_DB_NAME}"
            )
        return "sqlite+aiosqlite:///./dev.db"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
