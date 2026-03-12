# app/dependencies/rbac.py
from __future__ import annotations
from dataclasses import dataclass
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies.auth import get_current_user
from app.dependencies.db import get_db
from app.models.user import User
from app.models.workspace import WorkspaceMember, WorkspaceRoleEnum

_ROLE_RANK: dict[WorkspaceRoleEnum, int] = {
    WorkspaceRoleEnum.DOCTOR: 0,
    WorkspaceRoleEnum.ADMIN: 1,
    WorkspaceRoleEnum.OWNER: 2,
}


@dataclass(frozen=True, slots=True)
class WorkspaceContext:
    workspace_id: str
    member_id: str
    role: WorkspaceRoleEnum
    user: User


def _require_workspace_id(
    x_workspace_id: str | None = Header(None, alias="X-Workspace-Id"),
) -> str:
    if not x_workspace_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Workspace-Id header is required.",
        )
    return x_workspace_id


def require_workspace_role(*allowed_roles: WorkspaceRoleEnum):
    min_rank = min(_ROLE_RANK[r] for r in allowed_roles)

    async def _checker(
        workspace_id: str = Depends(_require_workspace_id),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> WorkspaceContext:
        result = await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.user_id == current_user.id,
                WorkspaceMember.workspace_id == workspace_id,
            )
        )
        member = result.scalar_one_or_none()
        if not member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of this workspace.",
            )
        caller_rank = _ROLE_RANK.get(WorkspaceRoleEnum(member.role), -1)
        if caller_rank < min_rank:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires one of: {[r.value for r in allowed_roles]}.",
            )
        return WorkspaceContext(
            workspace_id=workspace_id,
            member_id=member.id,
            role=WorkspaceRoleEnum(member.role),
            user=current_user,
        )

    return _checker