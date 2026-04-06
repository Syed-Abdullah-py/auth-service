# main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.db.session import async_engine
from app.domains.auth.router import router as auth_router
from app.domains.workspaces.router import router as workspaces_router
from app.domains.patients.router import router as patients_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await async_engine.dispose()


app = FastAPI(
    title="NeuroScan API",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "X-Workspace-Id"],
)

app.include_router(auth_router, prefix="/auth")
app.include_router(workspaces_router, prefix="/workspaces")
app.include_router(patients_router, prefix="/patients")


@app.get("/health", tags=["system"])
async def health_check() -> dict:
    return {"status": "ok", "version": "2.0.0"}