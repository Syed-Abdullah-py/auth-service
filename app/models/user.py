import enum
import uuid
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, String
from sqlalchemy.orm import relationship
from app.db.base import Base


def _gen_id() -> str:
    return str(uuid.uuid4())


class GlobalRoleEnum(str, enum.Enum):
    ADMIN = "ADMIN"
    RADIOLOGIST = "RADIOLOGIST"


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=_gen_id)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    name = Column(String, nullable=True)
    global_role = Column(String, nullable=True)

    # Professional
    medical_license_id = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    face_encoding = Column(String, nullable=True)

    # Extended profile
    cnic = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    city = Column(String, nullable=True)
    pin = Column(String, nullable=True)
    gender = Column(String, nullable=True)
    terms_accepted = Column(Boolean, default=False)

    # Verification
    is_verified = Column(Boolean, default=False)
    verification_otp = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    memberships = relationship(
        "WorkspaceMember", back_populates="user", cascade="all, delete-orphan"
    )
    owned_workspaces = relationship("Workspace", back_populates="owner")
    join_requests = relationship("JoinRequest", back_populates="user")


class PendingUser(Base):
    __tablename__ = "pending_users"

    id = Column(String, primary_key=True, default=_gen_id)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    name = Column(String, nullable=True)
    global_role = Column(String, nullable=True)
    verification_otp = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)