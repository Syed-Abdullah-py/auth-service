import enum
import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship
from app.db.base import Base


def _gen_id() -> str:
    return str(uuid.uuid4())


class RequestStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Invitation(Base):
    __tablename__ = "invitations"

    id = Column(String, primary_key=True, default=_gen_id)
    email = Column(String, nullable=False)
    token = Column(String, unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)

    workspace = relationship("Workspace", back_populates="invitations")


class JoinRequest(Base):
    __tablename__ = "join_requests"

    id = Column(String, primary_key=True, default=_gen_id)
    status = Column(String, default=RequestStatusEnum.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)

    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)

    user = relationship("User", back_populates="join_requests")
    workspace = relationship("Workspace", back_populates="join_requests")