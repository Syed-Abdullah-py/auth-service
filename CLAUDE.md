# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

NeuroScan auth-service is a FastAPI backend (v2.0.0) providing authentication, workspace management, patient records, and case tracking for a medical imaging platform. The database is PostgreSQL hosted on Supabase, accessed via asyncpg (async) and psycopg2 (sync/Alembic).

## Environment Setup

Copy `.env` and populate these variables:

```
SECRET_KEY=
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
SUPABASE_DB_USER=
SUPABASE_DB_PASSWORD=
SUPABASE_DB_HOST=
SUPABASE_DB_PORT=5432
SUPABASE_DB_NAME=
SUPABASE_DB_PREPARE_STATEMENTS=false
ENVIRONMENT=development
CORS_ORIGINS=["http://localhost:3000"]
```

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run dev server (reload on change)
uvicorn main:app --reload

# Run with Docker Compose
docker compose up

# Database migrations
alembic upgrade head                          # apply all migrations
alembic revision --autogenerate -m "message"  # generate new migration
alembic downgrade -1                          # roll back one step
```

API docs are available at `http://localhost:8000/docs` (disabled in production).

## Architecture

The app follows a **vertical-slice / domain-driven** layout under `app/domains/`. Each domain owns its `router.py`, `service.py`, and `schemas.py`. Models and DB plumbing live outside the domains.

```
main.py                  # FastAPI app, router registration, CORS, lifespan
app/
  core/
    config.py            # Settings via pydantic-settings, loaded from .env
    event_bus.py         # In-process SSE pub/sub (singleton: event_bus)
  db/
    base.py              # SQLAlchemy declarative Base
    session.py           # async_engine + AsyncSessionLocal
    migrations/          # Alembic env and versioned migrations
  models/                # SQLAlchemy ORM models (imported by Alembic via db/base.py)
  dependencies/
    db.py                # get_db - yields AsyncSession
    auth.py              # get_current_user - JWT bearer dependency
    rbac.py              # require_workspace_role(*roles) - workspace-scoped authz
  domains/
    auth/                # register, verify-otp, resend-otp, login, /me
    workspaces/          # workspace CRUD, members, invitations, join requests, SSE
    patients/            # patient CRUD (workspace-scoped)
    cases/               # case CRUD (workspace-scoped)
```

## Key Patterns

**Auth flow:** `POST /auth/register` creates a `PendingUser` with an OTP. `POST /auth/verify-otp` promotes it to a `User` and returns a JWT. All subsequent requests use `Authorization: Bearer <token>`.

**Workspace RBAC:** Workspace-protected routes use `require_workspace_role(*roles)` as a FastAPI dependency. The caller must pass an `X-Workspace-Id` header. Role hierarchy: `DOCTOR (0) < ADMIN (1) < OWNER (2)`. The dependency returns a `WorkspaceContext` dataclass with `workspace_id`, `member_id`, `role`, and `user`.

**SSE / EventBus:** `GET /workspaces/{id}/events` streams server-sent events. All internal workspace mutations should `await event_bus.publish(WorkspaceEvent(...))`. Import and use only the `event_bus` singleton - never instantiate `EventBus` directly.

**Database:** The async engine connects to Supabase with `ssl=require` and `statement_cache_size=0` (required for Supabase connection pooling). Alembic uses a separate sync psycopg2 URL. All PKs are UUIDs stored as strings.

**Two-user model:** Unverified registrations live in `pending_users`; verified accounts are in `users`. This separation keeps the auth flow clean without nullable columns on the main users table.