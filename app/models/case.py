import enum
import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship
from app.db.base import Base



def _gen_id() -> str:
    return str(uuid.uuid4())


class CaseStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    REVIEWED = "REVIEWED"


class CasePriorityEnum(str, enum.Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class Case(Base):
    __tablename__ = "cases"

    id = Column(String, primary_key=True, default=_gen_id)
    status = Column(String, default=CaseStatusEnum.PENDING)
    priority = Column(String, default=CasePriorityEnum.NORMAL)
    file_references = Column(Text, nullable=False)  # JSON string
    verdict = Column(String, nullable=True)
    verdict_updated_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)

    survival_prediction = Column(String, nullable=True)  # Short | Mid | Long

    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    assigned_to_member_id = Column(
        String, ForeignKey("workspace_members.id"), nullable=True
    )
    # Stable reference to the assigned doctor's user account; survives membership changes
    assigned_to_user_id = Column(
        String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    patient = relationship("Patient", back_populates="cases")
    assigned_to = relationship("WorkspaceMember", back_populates="assigned_cases")
    assigned_to_user = relationship("User", foreign_keys=[assigned_to_user_id])