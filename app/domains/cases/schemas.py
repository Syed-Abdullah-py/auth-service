from datetime import datetime
from pydantic import BaseModel
from app.models.case import CaseStatusEnum, CasePriorityEnum


class CaseUpdate(BaseModel):
    status: CaseStatusEnum | None = None
    priority: CasePriorityEnum | None = None
    verdict: str | None = None
    notes: str | None = None
    assigned_to_member_id: str | None = None


class CaseResponse(BaseModel):
    id: str
    status: str
    priority: str
    file_references: str  # JSON array of URLs
    verdict: str | None = None
    verdict_updated_at: datetime | None = None
    notes: str | None = None
    patient_id: str
    assigned_to_member_id: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CaseStatsResponse(BaseModel):
    total: int
    pending: int
    processing: int
    reviewed: int