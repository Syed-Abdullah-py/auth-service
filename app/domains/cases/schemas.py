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
    survival_prediction: str | None = None
    patient_id: str
    patient_first_name: str | None = None
    patient_last_name: str | None = None
    assigned_to_member_id: str | None = None
    assigned_to_user_id: str | None = None
    assigned_to_name: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_case(cls, case) -> "CaseResponse":
        assigned_user = getattr(case, "assigned_to_user", None)
        assigned_name = None
        if assigned_user:
            assigned_name = assigned_user.name or assigned_user.email
        return cls(
            id=case.id,
            status=case.status,
            priority=case.priority,
            file_references=case.file_references,
            verdict=case.verdict,
            verdict_updated_at=case.verdict_updated_at,
            notes=case.notes,
            survival_prediction=case.survival_prediction,
            patient_id=case.patient_id,
            patient_first_name=case.patient.first_name if case.patient else None,
            patient_last_name=case.patient.last_name if case.patient else None,
            assigned_to_member_id=case.assigned_to_member_id,
            assigned_to_user_id=case.assigned_to_user_id,
            assigned_to_name=assigned_name,
            created_at=case.created_at,
            updated_at=case.updated_at,
        )

    class Config:
        from_attributes = True


class CaseStatsResponse(BaseModel):
    total: int
    pending: int
    processing: int
    reviewed: int