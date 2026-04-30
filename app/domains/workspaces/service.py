# app/domains/workspaces/service.py
import logging
import re
import uuid
from datetime import datetime, timedelta
from functools import lru_cache

from async_lru import alru_cache
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.event_bus import EventBus, WorkspaceEvent, event_bus
from app.dependencies.rbac import WorkspaceContext
from app.domains.workspaces.schemas import (
    InvitationCreate,
    WorkspaceCreate,
    WorkspaceUpdate,
)
from app.models.invitation import Invitation, JoinRequest, RequestStatusEnum
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceRoleEnum
from app.models.case import Case

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1024)
def _make_slug(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "-", slug)
    return slug.strip("-")


async def _unique_slug(db: AsyncSession, name: str) -> str:
    base = _make_slug(name)
    slug = base
    counter = 1
    while True:
        result = await db.execute(select(Workspace).where(Workspace.slug == slug))
        if not result.scalar_one_or_none():
            return slug
        slug = f"{base}-{counter}"
        counter += 1


# ── Workspace CRUD ────────────────────────────────────────────────────────────


async def get_my_workspaces(db: AsyncSession, user: User) -> list:
    result = await db.execute(
        select(WorkspaceMember)
        .where(WorkspaceMember.user_id == user.id)
        .options(selectinload(WorkspaceMember.workspace))
    )
    memberships = result.scalars().all()
    return [
        {
            "id": m.id,
            "workspace_id": m.workspace_id,
            "workspace_name": m.workspace.name,
            "role": m.role,
            "joined_at": m.joined_at,
        }
        for m in memberships
    ]


async def create_workspace(
    db: AsyncSession, payload: WorkspaceCreate, user: User
) -> Workspace:
    if user.global_role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only global Admins can create workspaces.",
        )

    slug = await _unique_slug(db, payload.name)

    workspace = Workspace(name=payload.name, slug=slug, owner_id=user.id)
    db.add(workspace)
    await db.flush()  # Get workspace.id before adding membership

    membership = WorkspaceMember(
        user_id=user.id,
        workspace_id=workspace.id,
        role=WorkspaceRoleEnum.OWNER,
    )
    db.add(membership)
    await db.commit()
    await db.refresh(workspace)
    return workspace


async def update_workspace(
    db: AsyncSession, workspace_id: str, payload: WorkspaceUpdate, ctx: WorkspaceContext
) -> Workspace:
    if ctx.role != WorkspaceRoleEnum.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the workspace Owner can edit workspace details.",
        )

    result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id)
    )
    workspace = result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found.")

    workspace.name = payload.name
    await db.commit()
    await db.refresh(workspace)
    return workspace


async def delete_workspace(
    db: AsyncSession, workspace_id: str, ctx: WorkspaceContext
) -> None:
    if ctx.role != WorkspaceRoleEnum.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the workspace Owner can delete the workspace.",
        )

    result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id)
    )
    workspace = result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found.")

    await db.delete(workspace)
    await db.commit()


# ── Members ───────────────────────────────────────────────────────────────────


async def get_members(db: AsyncSession, ctx: WorkspaceContext) -> list:
    result = await db.execute(
        select(WorkspaceMember)
        .where(WorkspaceMember.workspace_id == ctx.workspace_id)
        .options(selectinload(WorkspaceMember.user))
        .options(selectinload(WorkspaceMember.workspace))
    )
    members = result.scalars().all()
    return [
        {
            "id": m.id,
            "workspace_id": m.workspace_id,
            "role": m.role,
            "joined_at": m.joined_at,
            "workspace_name": m.workspace.name,
            "user_id": m.user.id,
            "user_name": m.user.name,
            "user_email": m.user.email,
            "user_avatar_url": m.user.avatar_url,
        }
        for m in members
    ]


async def remove_member(
    db: AsyncSession, workspace_id: str, user_id: str, ctx: WorkspaceContext
) -> None:
    is_self = ctx.user.id == user_id

    if not is_self:
        if ctx.role not in (WorkspaceRoleEnum.OWNER, WorkspaceRoleEnum.ADMIN):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only OWNER or ADMIN can remove members.",
            )

    result = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.workspace_id == workspace_id,
        )
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Member not found.")

    if target.role == WorkspaceRoleEnum.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot remove the workspace Owner. Transfer ownership first.",
        )

    if (
        not is_self
        and ctx.role == WorkspaceRoleEnum.ADMIN
        and target.role == WorkspaceRoleEnum.ADMIN
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins cannot remove other Admins.",
        )

    # Null the member FK to avoid FK violations on delete; preserve assigned_to_user_id so
    # the doctor's name remains on the case and their cases reappear if they rejoin.
    cases = await db.execute(
        select(Case).where(Case.assigned_to_member_id == target.id)
    )
    for case in cases.scalars().all():
        case.assigned_to_member_id = None

    await db.delete(target)
    await db.commit()

    await event_bus.publish(
        WorkspaceEvent(
            type="member.removed",
            workspace_id=workspace_id,
            payload={"user_id": user_id},
        )
    )


# ── Invitations ───────────────────────────────────────────────────────────────


async def create_invitation(
    db: AsyncSession, workspace_id: str, payload: InvitationCreate, ctx: WorkspaceContext
) -> Invitation:
    if ctx.role not in (WorkspaceRoleEnum.OWNER, WorkspaceRoleEnum.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only OWNER or ADMIN can send invitations.",
        )

    # Block if already a member
    existing_user = await db.execute(
        select(User).where(User.email == payload.email)
    )
    existing_user = existing_user.scalar_one_or_none()
    if existing_user:
        is_member = await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.user_id == existing_user.id,
                WorkspaceMember.workspace_id == workspace_id,
            )
        )
        if is_member.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail="This user is already a member of this workspace.",
            )

    # Upsert invitation - refresh if already pending
    result = await db.execute(
        select(Invitation).where(
            Invitation.email == payload.email,
            Invitation.workspace_id == workspace_id,
        )
    )
    invitation = result.scalar_one_or_none()

    if invitation:
        invitation.token = str(uuid.uuid4())
        invitation.expires_at = datetime.utcnow() + timedelta(days=7)
    else:
        invitation = Invitation(
            email=payload.email,
            token=str(uuid.uuid4()),
            expires_at=datetime.utcnow() + timedelta(days=7),
            workspace_id=workspace_id,
        )
        db.add(invitation)

    await db.commit()
    await db.refresh(invitation)

    await event_bus.publish(
        WorkspaceEvent(
            type="member.invited",
            workspace_id=workspace_id,
            payload={"email": payload.email},
        )
    )

    return invitation


async def get_workspace_invitations(
    db: AsyncSession, workspace_id: str, ctx: WorkspaceContext
) -> list[Invitation]:
    if ctx.role not in (WorkspaceRoleEnum.OWNER, WorkspaceRoleEnum.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only OWNER or ADMIN can view invitations.",
        )

    result = await db.execute(
        select(Invitation).where(Invitation.workspace_id == workspace_id)
    )
    return result.scalars().all()


async def get_my_invitations(db: AsyncSession, user: User) -> list:
    result = await db.execute(
        select(Invitation)
        .where(Invitation.email == user.email)
        .options(selectinload(Invitation.workspace))
    )
    invitations = result.scalars().all()
    return [
        {
            "id": inv.id,
            "email": inv.email,
            "workspace_id": inv.workspace_id,
            "workspace_name": inv.workspace.name,
            "expires_at": inv.expires_at,
        }
        for inv in invitations
    ]


async def accept_invitation(
    db: AsyncSession, invitation_id: str, user: User
) -> dict:
    result = await db.execute(
        select(Invitation).where(Invitation.id == invitation_id)
    )
    invitation = result.scalar_one_or_none()
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found.")

    if invitation.email.lower() != user.email.lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This invitation does not belong to you.",
        )

    if invitation.expires_at < datetime.utcnow():
        await db.delete(invitation)
        await db.commit()
        raise HTTPException(status_code=400, detail="Invitation has expired.")

    # Race condition guard
    existing = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.user_id == user.id,
            WorkspaceMember.workspace_id == invitation.workspace_id,
        )
    )
    if existing.scalar_one_or_none():
        await db.delete(invitation)
        await db.commit()
        return {"message": "You are already a member of this workspace."}

    # Role is derived from global_role - never trust the invitation payload
    new_role = (
        WorkspaceRoleEnum.ADMIN
        if user.global_role == "ADMIN"
        else WorkspaceRoleEnum.DOCTOR
    )

    membership = WorkspaceMember(
        user_id=user.id,
        workspace_id=invitation.workspace_id,
        role=new_role,
    )
    db.add(membership)
    await db.delete(invitation)
    await db.commit()
    await db.refresh(membership)

    await event_bus.publish(
        WorkspaceEvent(
            type="member.joined",
            workspace_id=invitation.workspace_id,
            payload={
                "member": {
                    "id": membership.id,
                    "user_id": user.id,
                    "name": user.name,
                    "email": user.email,
                    "role": new_role.value,
                }
            },
        )
    )

    return {"message": "Invitation accepted successfully."}


async def reject_invitation(
    db: AsyncSession, invitation_id: str, user: User
) -> dict:
    result = await db.execute(
        select(Invitation).where(Invitation.id == invitation_id)
    )
    invitation = result.scalar_one_or_none()
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found.")

    if invitation.email.lower() != user.email.lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This invitation does not belong to you.",
        )

    await db.delete(invitation)
    await db.commit()
    return {"message": "Invitation rejected."}


# ── Invitable Users ───────────────────────────────────────────────────────────

async def search_invitable_users(
    db: AsyncSession, workspace_id: str, q: str, ctx: WorkspaceContext
) -> list[User]:
    # Users already in the workspace
    member_ids_result = await db.execute(
        select(WorkspaceMember.user_id).where(WorkspaceMember.workspace_id == workspace_id)
    )
    member_ids = {row[0] for row in member_ids_result.all()}

    # Emails already invited (pending)
    invited_emails_result = await db.execute(
        select(Invitation.email).where(Invitation.workspace_id == workspace_id)
    )
    invited_emails = {row[0] for row in invited_emails_result.all()}

    query = select(User).where(User.id != ctx.user.id)

    if member_ids:
        query = query.where(User.id.notin_(member_ids))
    if invited_emails:
        query = query.where(User.email.notin_(invited_emails))

    if q:
        term = f"%{q.lower()}%"
        from sqlalchemy import or_, func
        query = query.where(
            or_(
                func.lower(User.email).like(term),
                func.lower(User.name).like(term),
            )
        )

    result = await db.execute(query.limit(20))
    return result.scalars().all()


# ── Join Requests ─────────────────────────────────────────────────────────────

@alru_cache(maxsize=256, ttl=300)
async def get_discoverable_workspaces(
    db: AsyncSession, user: User
) -> list[Workspace]:
    # Get workspace IDs the user already belongs to
    result = await db.execute(
        select(WorkspaceMember.workspace_id).where(
            WorkspaceMember.user_id == user.id
        )
    )
    joined_ids = [row[0] for row in result.all()]

    query = select(Workspace)
    if joined_ids:
        query = query.where(Workspace.id.notin_(joined_ids))

    result = await db.execute(query.limit(20))
    return result.scalars().all()


async def create_join_request(
    db: AsyncSession, workspace_id: str, user: User
) -> JoinRequest:
    # Block if already a member
    existing_member = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.user_id == user.id,
            WorkspaceMember.workspace_id == workspace_id,
        )
    )
    if existing_member.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already a member of this workspace.")

    # Return existing pending request instead of duplicating
    existing_request = await db.execute(
        select(JoinRequest).where(
            JoinRequest.user_id == user.id,
            JoinRequest.workspace_id == workspace_id,
            JoinRequest.status == RequestStatusEnum.PENDING,
        )
    )
    existing = existing_request.scalar_one_or_none()
    if existing:
        return existing

    join_request = JoinRequest(
        user_id=user.id,
        workspace_id=workspace_id,
        status=RequestStatusEnum.PENDING,
    )
    db.add(join_request)
    await db.commit()
    await db.refresh(join_request)
    return join_request


async def get_join_requests(
    db: AsyncSession, workspace_id: str, ctx: WorkspaceContext
) -> list:
    if ctx.role not in (WorkspaceRoleEnum.OWNER, WorkspaceRoleEnum.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only OWNER or ADMIN can view join requests.",
        )

    result = await db.execute(
        select(JoinRequest)
        .where(
            JoinRequest.workspace_id == workspace_id,
            JoinRequest.status == RequestStatusEnum.PENDING,
        )
        .options(
            selectinload(JoinRequest.user),
            selectinload(JoinRequest.workspace),
        )
    )
    requests = result.scalars().all()
    return [
        {
            "id": r.id,
            "workspace_id": r.workspace_id,
            "workspace_name": r.workspace.name,
            "user_id": r.user_id,
            "user_name": r.user.name,
            "user_email": r.user.email,
            "status": r.status,
            "created_at": r.created_at,
        }
        for r in requests
    ]


async def approve_join_request(
    db: AsyncSession, request_id: str, ctx: WorkspaceContext
) -> dict:
    result = await db.execute(
        select(JoinRequest).where(JoinRequest.id == request_id)
    )
    join_request = result.scalar_one_or_none()
    if not join_request:
        raise HTTPException(status_code=404, detail="Join request not found.")

    if ctx.role not in (WorkspaceRoleEnum.OWNER, WorkspaceRoleEnum.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only OWNER or ADMIN can approve join requests.",
        )

    # Get joining user to determine their role
    user_result = await db.execute(
        select(User).where(User.id == join_request.user_id)
    )
    joining_user = user_result.scalar_one_or_none()
    if not joining_user:
        raise HTTPException(status_code=404, detail="User not found.")

    new_role = (
        WorkspaceRoleEnum.ADMIN
        if joining_user.global_role == "ADMIN"
        else WorkspaceRoleEnum.DOCTOR
    )

    membership = WorkspaceMember(
        user_id=join_request.user_id,
        workspace_id=join_request.workspace_id,
        role=new_role,
    )
    db.add(membership)
    join_request.status = RequestStatusEnum.APPROVED
    await db.commit()

    await event_bus.publish(
        WorkspaceEvent(
            type="member.joined",
            workspace_id=join_request.workspace_id,
            payload={
                "member": {
                    "user_id": joining_user.id,
                    "name": joining_user.name,
                    "email": joining_user.email,
                    "role": new_role.value,
                }
            },
        )
    )

    return {"message": "Join request approved."}


async def reject_join_request(
    db: AsyncSession, request_id: str, ctx: WorkspaceContext
) -> dict:
    result = await db.execute(
        select(JoinRequest).where(JoinRequest.id == request_id)
    )
    join_request = result.scalar_one_or_none()
    if not join_request:
        raise HTTPException(status_code=404, detail="Join request not found.")

    if ctx.role not in (WorkspaceRoleEnum.OWNER, WorkspaceRoleEnum.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only OWNER or ADMIN can reject join requests.",
        )

    join_request.status = RequestStatusEnum.REJECTED
    await db.commit()
    return {"message": "Join request rejected."}