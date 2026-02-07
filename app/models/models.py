import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, JSON, Enum
from sqlalchemy.orm import relationship
from app.db.session import Base
import enum

def generate_id():
    return str(uuid.uuid4())

# Enums
class GlobalRoleEnum(str, enum.Enum):
    ADMIN = "ADMIN"
    RADIOLOGIST = "RADIOLOGIST"

class WorkspaceRoleEnum(str, enum.Enum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    DOCTOR = "DOCTOR"

class CaseStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"

class RequestStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    REJECTED = "REJECTED"
    APPROVED = "APPROVED"


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=generate_id)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    name = Column(String, nullable=True)

    # Professional details
    medical_license_id = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    face_encoding = Column(String, nullable=True) # Stored as JSON string? Or just string? Prisma said JSON string.
    global_role = Column(String, nullable=True) # "ADMIN" or "RADIOLOGIST"

    # Extended Profile
    cnic = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    city = Column(String, nullable=True)
    pin = Column(String, nullable=True)
    gender = Column(String, nullable=True)
    terms_accepted = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    memberships = relationship("WorkspaceMember", back_populates="user", cascade="all, delete-orphan")
    owned_workspaces = relationship("Workspace", back_populates="owner")
    join_requests = relationship("JoinRequest", back_populates="user")


class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(String, primary_key=True, default=generate_id)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, index=True, nullable=False)
    
    owner_id = Column(String, ForeignKey("users.id"), nullable=False)
    owner = relationship("User", back_populates="owned_workspaces")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    members = relationship("WorkspaceMember", back_populates="workspace", cascade="all, delete-orphan")
    patients = relationship("Patient", back_populates="workspace", cascade="all, delete-orphan")
    invitations = relationship("Invitation", back_populates="workspace", cascade="all, delete-orphan")
    join_requests = relationship("JoinRequest", back_populates="workspace", cascade="all, delete-orphan")


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"

    id = Column(String, primary_key=True, default=generate_id)
    role = Column(String, nullable=False) # OWNER, ADMIN, DOCTOR
    joined_at = Column(DateTime, default=datetime.utcnow)

    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)

    user = relationship("User", back_populates="memberships")
    workspace = relationship("Workspace", back_populates="members")
    
    assigned_cases = relationship("Case", back_populates="assigned_to")


class Patient(Base):
    __tablename__ = "patients"

    id = Column(String, primary_key=True, default=generate_id)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    workspace = relationship("Workspace", back_populates="patients")

    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    dob = Column(DateTime, nullable=False)
    gender = Column(String, nullable=False)
    phone_number = Column(String, nullable=False)
    mrn = Column(String, nullable=True)
    cnic = Column(String, nullable=True)
    address = Column(String, nullable=True)
    city = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    cases = relationship("Case", back_populates="patient", cascade="all, delete-orphan")


class Case(Base):
    __tablename__ = "cases"

    id = Column(String, primary_key=True, default=generate_id)
    status = Column(String, default="PENDING")
    priority = Column(String, default="normal")
    
    # Store file references as JSON
    file_references = Column(Text, nullable=False) # JSON string

    verdict = Column(String, nullable=True)
    verdict_updated_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)

    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    patient = relationship("Patient", back_populates="cases")

    assigned_to_member_id = Column(String, ForeignKey("workspace_members.id"), nullable=True)
    assigned_to = relationship("WorkspaceMember", back_populates="assigned_cases")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Invitation(Base):
    __tablename__ = "invitations"

    id = Column(String, primary_key=True, default=generate_id)
    email = Column(String, nullable=False)
    role = Column(String, nullable=False)
    token = Column(String, unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)

    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    workspace = relationship("Workspace", back_populates="invitations")


class JoinRequest(Base):
    __tablename__ = "join_requests"

    id = Column(String, primary_key=True, default=generate_id)
    status = Column(String, default="PENDING")
    created_at = Column(DateTime, default=datetime.utcnow)

    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    user = relationship("User", back_populates="join_requests")

    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    workspace = relationship("Workspace", back_populates="join_requests")
