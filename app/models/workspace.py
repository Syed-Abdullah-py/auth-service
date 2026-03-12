import enum
import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship
from app.db.base import Base


def _gen_id() -> str:
    return str(uuid.uuid4())


class WorkspaceRoleEnum(str, enum.Enum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    DOCTOR = "DOCTOR"


class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(String, primary_key=True, default=_gen_id)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, index=True, nullable=False)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="owned_workspaces")
    members = relationship(
        "WorkspaceMember", back_populates="workspace", cascade="all, delete-orphan"
    )
    patients = relationship(
        "Patient", back_populates="workspace", cascade="all, delete-orphan"
    )
    invitations = relationship(
        "Invitation", back_populates="workspace", cascade="all, delete-orphan"
    )
    join_requests = relationship(
        "JoinRequest", back_populates="workspace", cascade="all, delete-orphan"
    )


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"

    id = Column(String, primary_key=True, default=_gen_id)
    role = Column(String, nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow)

    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)

    user = relationship("User", back_populates="memberships")
    workspace = relationship("Workspace", back_populates="members")
    assigned_cases = relationship("Case", back_populates="assigned_to")