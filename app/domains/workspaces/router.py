# app/domains/workspaces/router.py
import asyncio

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_bus import event_bus
from app.dependencies.auth import get_current_user
from app.dependencies.db import get_db
from app.dependencies.rbac import WorkspaceContext, require_workspace_role
from app.domains.workspaces import service
from app.domains.workspaces.schemas import (
    InvitationCreate,
    InvitationResponse,
    JoinRequestResponse,
    MemberResponse,
    MessageResponse,
    MyWorkspacesResponse,
    WorkspaceCreate,
    WorkspaceResponse,
    WorkspaceUpdate,
)
from app.models.user import User
from app.models.workspace import WorkspaceRoleEnum

router = APIRouter(tags=["workspaces"])


# ── Workspace CRUD ────────────────────────────────────────────────────────────


@router.get("/", response_model=list[MyWorkspacesResponse])
async def get_my_workspaces(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_my_workspaces(db, current_user)


@router.post("/", response_model=WorkspaceResponse, status_code=201)
async def create_workspace(
    payload: WorkspaceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.create_workspace(db, payload, current_user)


@router.put("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: str,
    payload: WorkspaceUpdate,
    ctx: WorkspaceContext = Depends(
        require_workspace_role(WorkspaceRoleEnum.OWNER)
    ),
    db: AsyncSession = Depends(get_db),
):
    return await service.update_workspace(db, workspace_id, payload, ctx)


@router.delete("/{workspace_id}", status_code=204)
async def delete_workspace(
    workspace_id: str,
    ctx: WorkspaceContext = Depends(
        require_workspace_role(WorkspaceRoleEnum.OWNER)
    ),
    db: AsyncSession = Depends(get_db),
):
    await service.delete_workspace(db, workspace_id, ctx)


# ── SSE — must be defined before /{workspace_id}/members to avoid route clash ──


@router.get("/{workspace_id}/events")
async def workspace_event_stream(
    ctx: WorkspaceContext = Depends(
        require_workspace_role(
            WorkspaceRoleEnum.DOCTOR,
            WorkspaceRoleEnum.ADMIN,
            WorkspaceRoleEnum.OWNER,
        )
    ),
) -> StreamingResponse:
    async def stream():
        q = event_bus.subscribe(ctx.workspace_id)
        try:
            yield ": heartbeat\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=30.0)
                    yield event.to_sse()
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            event_bus.unsubscribe(ctx.workspace_id, q)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ── Members ───────────────────────────────────────────────────────────────────


@router.get("/{workspace_id}/members", response_model=list[MemberResponse])
async def get_members(
    workspace_id: str,
    ctx: WorkspaceContext = Depends(
        require_workspace_role(
            WorkspaceRoleEnum.DOCTOR,
            WorkspaceRoleEnum.ADMIN,
            WorkspaceRoleEnum.OWNER,
        )
    ),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_members(db, ctx)


@router.delete("/{workspace_id}/members/{user_id}", status_code=204)
async def remove_member(
    workspace_id: str,
    user_id: str,
    ctx: WorkspaceContext = Depends(
        require_workspace_role(
            WorkspaceRoleEnum.DOCTOR,
            WorkspaceRoleEnum.ADMIN,
            WorkspaceRoleEnum.OWNER,
        )
    ),
    db: AsyncSession = Depends(get_db),
):
    await service.remove_member(db, workspace_id, user_id, ctx)


# ── Invitations ───────────────────────────────────────────────────────────────


@router.post("/{workspace_id}/invitations", response_model=InvitationResponse, status_code=201)
async def create_invitation(
    workspace_id: str,
    payload: InvitationCreate,
    ctx: WorkspaceContext = Depends(
        require_workspace_role(WorkspaceRoleEnum.ADMIN, WorkspaceRoleEnum.OWNER)
    ),
    db: AsyncSession = Depends(get_db),
):
    return await service.create_invitation(db, workspace_id, payload, ctx)


@router.get("/{workspace_id}/invitations", response_model=list[InvitationResponse])
async def get_workspace_invitations(
    workspace_id: str,
    ctx: WorkspaceContext = Depends(
        require_workspace_role(WorkspaceRoleEnum.ADMIN, WorkspaceRoleEnum.OWNER)
    ),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_workspace_invitations(db, workspace_id, ctx)


@router.get("/invitations/mine", response_model=list[InvitationResponse])
async def get_my_invitations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_my_invitations(db, current_user)


@router.post("/invitations/{invitation_id}/accept", response_model=MessageResponse)
async def accept_invitation(
    invitation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.accept_invitation(db, invitation_id, current_user)


@router.post("/invitations/{invitation_id}/reject", response_model=MessageResponse)
async def reject_invitation(
    invitation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.reject_invitation(db, invitation_id, current_user)


# ── Join Requests ─────────────────────────────────────────────────────────────


@router.get("/discover", response_model=list[WorkspaceResponse])
async def get_discoverable_workspaces(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_discoverable_workspaces(db, current_user)


@router.post("/{workspace_id}/join-requests", response_model=JoinRequestResponse, status_code=201)
async def create_join_request(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.create_join_request(db, workspace_id, current_user)


@router.get("/{workspace_id}/join-requests", response_model=list[JoinRequestResponse])
async def get_join_requests(
    workspace_id: str,
    ctx: WorkspaceContext = Depends(
        require_workspace_role(WorkspaceRoleEnum.ADMIN, WorkspaceRoleEnum.OWNER)
    ),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_join_requests(db, workspace_id, ctx)


@router.post("/join-requests/{request_id}/approve", response_model=MessageResponse)
async def approve_join_request(
    request_id: str,
    ctx: WorkspaceContext = Depends(
        require_workspace_role(WorkspaceRoleEnum.ADMIN, WorkspaceRoleEnum.OWNER)
    ),
    db: AsyncSession = Depends(get_db),
):
    return await service.approve_join_request(db, request_id, ctx)


@router.post("/join-requests/{request_id}/reject", response_model=MessageResponse)
async def reject_join_request(
    request_id: str,
    ctx: WorkspaceContext = Depends(
        require_workspace_role(WorkspaceRoleEnum.ADMIN, WorkspaceRoleEnum.OWNER)
    ),
    db: AsyncSession = Depends(get_db),
):
    return await service.reject_join_request(db, request_id, ctx)