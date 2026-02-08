from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.models import User, Case, WorkspaceMember, Patient, CaseStatusEnum
from app.api.deps import get_db, get_current_user

router = APIRouter()

@router.get("/cases/stats")
def get_doctor_stats(
    workspace_id: Optional[str] = Header(None, alias="X-Workspace-Id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not workspace_id:
        # Returning zeros if no workspace context provided
        return {"totalCases": 0, "pendingCases": 0, "completedCases": 0}

    # Find membership for this user in this workspace
    member = db.query(WorkspaceMember).filter(
        WorkspaceMember.user_id == current_user.id,
        WorkspaceMember.workspace_id == workspace_id
    ).first()

    if not member:
         return {"totalCases": 0, "pendingCases": 0, "completedCases": 0}

    total_cases = db.query(Case).filter(Case.assigned_to_member_id == member.id).count()
    pending_cases = db.query(Case).filter(
        Case.assigned_to_member_id == member.id, 
        Case.status == CaseStatusEnum.PENDING
    ).count()
    completed_cases = db.query(Case).filter(
        Case.assigned_to_member_id == member.id, 
        Case.status == CaseStatusEnum.COMPLETED
    ).count()

    return {
        "totalCases": total_cases,
        "pendingCases": pending_cases,
        "completedCases": completed_cases
    }

@router.get("/cases/recent")
def get_recent_cases(
    workspace_id: Optional[str] = Header(None, alias="X-Workspace-Id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not workspace_id:
        return []

    member = db.query(WorkspaceMember).filter(
        WorkspaceMember.user_id == current_user.id,
        WorkspaceMember.workspace_id == workspace_id
    ).first()

    if not member:
        return []

    cases = db.query(Case).filter(
        Case.assigned_to_member_id == member.id
    ).order_by(Case.updated_at.desc()).limit(5).all()

    # We need to include patient info manually or via join if lazy loading issue
    # For now, let's just return basic info, assuming frontend needs patient name
    
    results = []
    for c in cases:
        # Assuming relationship is loaded or accessible
        # If lazy loading fails without async, we might need options(joinedload)
        # But this is sync sqlalchemy, so lazy loading works if session is open
        patient_name = f"{c.patient.first_name} {c.patient.last_name}" if c.patient else "Unknown"
        
        results.append({
            "id": c.id,
            "status": c.status,
            "priority": c.priority,
            "updatedAt": c.updated_at,
            "patient": {
                "connect": { "id": c.patient_id }, # Format for frontend? or simplified?
                "name": patient_name,
                "first_name": c.patient.first_name if c.patient else "",
                "last_name": c.patient.last_name if c.patient else ""
            },
            "verdict": c.verdict
        })
        
    return results
