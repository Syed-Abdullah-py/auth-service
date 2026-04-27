# main.py
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.db.session import async_engine
from app.domains.auth.router import router as auth_router
from app.domains.workspaces.router import router as workspaces_router
from app.domains.patients.router import router as patients_router
from app.domains.cases.router import router as cases_router


def _run_migrations() -> None:
    from alembic.config import Config
    from alembic import command
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.USE_LOCAL_DB:
        await asyncio.to_thread(_run_migrations)
    yield
    await async_engine.dispose()


app = FastAPI(
    title="NeuroScan API",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
)

_wildcard = settings.CORS_ORIGINS == ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=r".*" if _wildcard else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "X-Workspace-Id"],
)

app.include_router(auth_router, prefix="/auth")
app.include_router(workspaces_router, prefix="/workspaces")
app.include_router(patients_router, prefix="/patients")
app.include_router(cases_router, prefix="/cases")


@app.get("/health", tags=["system"])
async def health_check() -> dict:
    return {"status": "ok", "version": "2.0.0"}