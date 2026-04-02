# app/domains/workspaces/schemas.py
from pydantic import BaseModel, EmailStr
from datetime import datetime
from app.models.workspace import WorkspaceRoleEnum


class WorkspaceCreate(BaseModel):
    name: str

class WorkspaceUpdate(BaseModel):
    name: str

class WorkspaceResponse(BaseModel):
    id: str
    name: str
    slug: str
    owner_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class MemberResponse(BaseModel):
    id: str
    workspace_id: str
    role: WorkspaceRoleEnum
    joined_at: datetime
    workspace_name: str | None = None
    user_id: str | None = None
    user_name: str | None = None
    user_email: str | None = None
    user_avatar_url: str | None = None

    class Config:
        from_attributes = True


class MyWorkspacesResponse(BaseModel):
    id: str
    workspace_id: str
    workspace_name: str
    role: WorkspaceRoleEnum
    joined_at: datetime

    class Config:
        from_attributes = True


class InvitationCreate(BaseModel):
    email: EmailStr


class InvitationResponse(BaseModel):
    id: str
    email: str
    workspace_id: str
    workspace_name: str | None = None
    expires_at: datetime

    class Config:
        from_attributes = True


class JoinRequestResponse(BaseModel):
    id: str
    workspace_id: str
    workspace_name: str | None = None
    user_id: str
    user_name: str | None = None
    user_email: str | None = None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    message: str