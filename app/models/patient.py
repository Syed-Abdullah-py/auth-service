import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, String, Date
from sqlalchemy.orm import relationship
from app.db.base import Base


def _gen_id() -> str:
    return str(uuid.uuid4())


class Patient(Base):
    __tablename__ = "patients"

    id = Column(String, primary_key=True, default=_gen_id)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)

    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    dob = Column(Date, nullable=False)
    gender = Column(String, nullable=False)
    phone_number = Column(String, nullable=False)
    mrn = Column(String, nullable=True)
    cnic = Column(String, nullable=True)
    address = Column(String, nullable=True)
    city = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    workspace = relationship("Workspace", back_populates="patients")
    cases = relationship("Case", back_populates="patient", cascade="all, delete-orphan")