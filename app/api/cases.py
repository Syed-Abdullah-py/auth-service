from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime

from app.models.models import User, Case, WorkspaceMember, Patient, CaseStatusEnum
from app.schemas.schemas import CaseCreate, CaseUpdate, CaseResponse
from app.api.deps import get_db, get_current_user

router = APIRouter()

# --- Helpers ---
def get_member_in_workspace(db: Session, user_id: str, workspace_id: str):
    member = db.query(WorkspaceMember).filter(
        WorkspaceMember.user_id == user_id,
        WorkspaceMember.workspace_id == workspace_id
    ).first()
    return member

# --- Routes ---

@router.get("/cases", response_model=List[CaseResponse])
def get_cases(
    skip: int = 0,
    limit: int = 100,
    assigned_to: Optional[str] = None, # 'me' or member_id
    workspace_id: Optional[str] = Header(None, alias="X-Workspace-Id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not workspace_id:
        return []

    # Verify membership
    member = get_member_in_workspace(db, current_user.id, workspace_id)
    if not member:
        raise HTTPException(status_code=403, detail="Not a member of this workspace")

    # Start query
    query = db.query(Case).join(Patient).filter(
        Patient.workspace_id == workspace_id
    )

    # Apply filters
    if assigned_to:
        if assigned_to == 'me':
            query = query.filter(Case.assigned_to_member_id == member.id)
        else:
            query = query.filter(Case.assigned_to_member_id == assigned_to)

    cases = query.order_by(Case.created_at.desc()).offset(skip).limit(limit).all()
    return cases

@router.post("/cases", response_model=CaseResponse)
def create_case(
    case_in: CaseCreate,
    workspace_id: Optional[str] = Header(None, alias="X-Workspace-Id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not workspace_id:
        raise HTTPException(status_code=400, detail="Workspace ID required")

    member = get_member_in_workspace(db, current_user.id, workspace_id)
    if not member:
        raise HTTPException(status_code=403, detail="Not a member of this workspace")

    if member.role not in ["OWNER", "ADMIN"]:
        raise HTTPException(status_code=403, detail="Only Admins or Owners can create cases")

    # Verify patient belongs to workspace
    patient = db.query(Patient).filter(Patient.id == case_in.patient_id, Patient.workspace_id == workspace_id).first()
    if not patient:
         raise HTTPException(status_code=404, detail="Patient not found in this workspace")

    db_case = Case(
        **case_in.dict(exclude={"assigned_to_member_id"}), # Handle assignment separately if needed or allow direct
        assigned_to_member_id=member.id # Auto-assign to creator? Or leave null? Schema suggests explicit via update or input.
        # Let's check schema: CaseBase has assigned_to_member_id optional.
        # If passed in payload, use it. If not, maybe default to creator or None.
        # `case_in.dict()` includes assigned_to_member_id.
    )
    
    # Override assignment if provided, else default to None or logic?
    # Using specific logic:
    if case_in.assigned_to_member_id:
        db_case.assigned_to_member_id = case_in.assigned_to_member_id
    
    db.add(db_case)
    db.commit()
    db.refresh(db_case)
    return db_case

@router.get("/cases/stats")
def get_doctor_stats(
    workspace_id: Optional[str] = Header(None, alias="X-Workspace-Id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not workspace_id:
        return {"totalCases": 0, "pendingCases": 0, "completedCases": 0}

    member = get_member_in_workspace(db, current_user.id, workspace_id)
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

    member = get_member_in_workspace(db, current_user.id, workspace_id)
    if not member:
        return []

    cases = db.query(Case).filter(
        Case.assigned_to_member_id == member.id
    ).order_by(Case.updated_at.desc()).limit(5).all()
    
    results = []
    for c in cases:
        patient_name = f"{c.patient.first_name} {c.patient.last_name}" if c.patient else "Unknown"
        results.append({
            "id": c.id,
            "status": c.status,
            "priority": c.priority,
            "updatedAt": c.updated_at,
            "patient": {
                "connect": { "id": c.patient_id },
                "name": patient_name,
                "first_name": c.patient.first_name if c.patient else "",
                "last_name": c.patient.last_name if c.patient else ""
            },
            "verdict": c.verdict
        })
        
    return results

@router.get("/cases/{case_id}", response_model=CaseResponse)
def get_case(
    case_id: str,
    workspace_id: Optional[str] = Header(None, alias="X-Workspace-Id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
        
    # Verify access via workspace
    if workspace_id and case.patient.workspace_id != workspace_id:
         raise HTTPException(status_code=403, detail="Access denied")
         
    return case

@router.put("/cases/{case_id}", response_model=CaseResponse)
def update_case(
    case_id: str,
    case_in: CaseUpdate,
    workspace_id: Optional[str] = Header(None, alias="X-Workspace-Id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
        
    # Verify access
    if workspace_id and case.patient.workspace_id != workspace_id:
         raise HTTPException(status_code=403, detail="Access denied")

    member = get_member_in_workspace(db, current_user.id, case.patient.workspace_id)
    if not member:
        raise HTTPException(status_code=403, detail="Not a member")

    update_data = case_in.dict(exclude_unset=True)

    if member.role == "DOCTOR":
        # Doctors can only update their assigned cases and only specific fields
        if case.assigned_to_member_id != member.id:
             raise HTTPException(status_code=403, detail="Doctors can only update assigned cases")
        
        allowed_fields = {"verdict", "notes", "status"}
        for field in update_data.keys():
            if field not in allowed_fields:
                raise HTTPException(status_code=403, detail=f"Doctors cannot update field: {field}")
    elif member.role not in ["OWNER", "ADMIN"]:
         raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    # If verdict is being updated, set verdict_updated_at
    if "verdict" in update_data:
        update_data["verdict_updated_at"] = datetime.utcnow()
        
    for field, value in update_data.items():
        setattr(case, field, value)
        
    db.commit()
    db.refresh(case)
    return case

@router.delete("/cases/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_case(
    case_id: str,
    workspace_id: Optional[str] = Header(None, alias="X-Workspace-Id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Verify access
    if workspace_id and case.patient.workspace_id != workspace_id:
         raise HTTPException(status_code=403, detail="Access denied")

    member = get_member_in_workspace(db, current_user.id, case.patient.workspace_id)
    if not member or member.role not in ["OWNER", "ADMIN"]:
         raise HTTPException(status_code=403, detail="Only Admins or Owners can delete cases")
         
    db.delete(case)
    db.commit()
    return None
