from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session
from datetime import datetime

from app.models.models import User, Patient, WorkspaceMember
from app.schemas.schemas import PatientCreate, PatientUpdate, PatientResponse
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

@router.get("/patients", response_model=List[PatientResponse])
def get_patients(
    skip: int = 0,
    limit: int = 100,
    phone_number: Optional[str] = None,
    workspace_id: Optional[str] = Header(None, alias="X-Workspace-Id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    print(f"[Patients API] get_patients called with workspace_id: {workspace_id}")
    print(f"[Patients API] current_user: {current_user.email}")
    
    if not workspace_id:
        print("[Patients API] No workspace_id, returning empty list")
        return []

    member = get_member_in_workspace(db, current_user.id, workspace_id)
    print(f"[Patients API] member found: {member is not None}")
    
    if not member:
        print(f"[Patients API] 403: User {current_user.id} is not a member of workspace {workspace_id}")
        raise HTTPException(status_code=403, detail="Not a member of this workspace")

    patients_query = db.query(Patient).filter(
        Patient.workspace_id == workspace_id
    )

    if phone_number:
        # Simple exact match for now. In production, we might want to normalize.
        patients_query = patients_query.filter(Patient.phone_number == phone_number)

    patients = patients_query.order_by(Patient.updated_at.desc()).offset(skip).limit(limit).all()
    
    print(f"[Patients API] Found {len(patients)} patients")

    return patients

@router.post("/patients", response_model=PatientResponse)
def create_patient(
    patient_in: PatientCreate,
    workspace_id: Optional[str] = Header(None, alias="X-Workspace-Id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not workspace_id:
        raise HTTPException(status_code=400, detail="Workspace ID required")

    member = get_member_in_workspace(db, current_user.id, workspace_id)
    if not member:
        print(f"[Patients API] Create: User {current_user.id} not in workspace {workspace_id}")
        raise HTTPException(status_code=403, detail="Not a member of this workspace")

    db_patient = Patient(
        **patient_in.dict(),
        workspace_id=workspace_id
    )

    # Allow DOCTOR, ADMIN, OWNER
    if member.role not in ["OWNER", "ADMIN", "DOCTOR"]:
        print(f"[Patients API] Create: Role {member.role} not allowed")
        raise HTTPException(status_code=403, detail="Only Team Members can create patients")
    
    db.add(db_patient)
    db.commit()
    db.refresh(db_patient)
    return db_patient

@router.get("/patients/{patient_id}", response_model=PatientResponse)
def get_patient(
    patient_id: str,
    workspace_id: Optional[str] = Header(None, alias="X-Workspace-Id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
        
    if workspace_id and patient.workspace_id != workspace_id:
         raise HTTPException(status_code=403, detail="Access denied")
         
    return patient

@router.put("/patients/{patient_id}", response_model=PatientResponse)
def update_patient(
    patient_id: str,
    patient_in: PatientUpdate,
    workspace_id: Optional[str] = Header(None, alias="X-Workspace-Id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
        
    if workspace_id and patient.workspace_id != workspace_id:
         raise HTTPException(status_code=403, detail="Access denied")

    member = get_member_in_workspace(db, current_user.id, patient.workspace_id)
    # Allow DOCTOR, ADMIN, OWNER
    if not member or member.role not in ["OWNER", "ADMIN", "DOCTOR"]:
        raise HTTPException(status_code=403, detail="Only Team Members can update patients")
         
    update_data = patient_in.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(patient, field, value)
    
    db.commit()
    db.refresh(patient)
    return patient

@router.delete("/patients/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_patient(
    patient_id: str,
    workspace_id: Optional[str] = Header(None, alias="X-Workspace-Id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    if workspace_id and patient.workspace_id != workspace_id:
         raise HTTPException(status_code=403, detail="Access denied")

    member = get_member_in_workspace(db, current_user.id, patient.workspace_id)
    if not member or member.role not in ["OWNER", "ADMIN"]:
        raise HTTPException(status_code=403, detail="Only Admins or Owners can delete patients")
         
    db.delete(patient)
    db.commit()
    return None
