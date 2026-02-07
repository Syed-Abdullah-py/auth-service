from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.models.models import User, Workspace, WorkspaceMembership, RoleEnum
from app.schemas.schemas import WorkspaceCreate, WorkspaceResponse, MembershipResponse
from app.api.deps import get_db, get_current_user

router = APIRouter()

@router.get("/workspaces", response_model=List[MembershipResponse])
def get_my_workspaces(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Fetch memberships for the current user
    # We return the workspace details along with the role
    memberships = db.query(WorkspaceMembership).filter(
        WorkspaceMembership.user_id == current_user.id
    ).all()
    
    results = []
    for m in memberships:
        results.append({
            "workspace_id": m.workspace.id,
            "name": m.workspace.name,
            "role": m.role
        })
    return results

@router.post("/workspaces", response_model=WorkspaceResponse)
def create_workspace(
    workspace: WorkspaceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 1. Create Workspace
    db_workspace = Workspace(name=workspace.name)
    db.add(db_workspace)
    db.commit()
    db.refresh(db_workspace)
    
    # 2. Add creator as OWNER
    membership = WorkspaceMembership(
        user_id=current_user.id,
        workspace_id=db_workspace.id,
        role=RoleEnum.OWNER
    )
    db.add(membership)
    db.commit()
    
    return {
        "id": db_workspace.id,
        "name": db_workspace.name,
        "role": RoleEnum.OWNER
    }

@router.post("/workspaces/{workspace_id}/members", response_model=MembershipResponse)
def add_member(
    workspace_id: int,
    email: str,
    role: RoleEnum,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Check if current user is owner of this workspace
    # Need to manually check here because this is a specific action on a workspace resource
    # Or reuse the dependency if we passed workspace_id in header, but here it is in path.
    # For MVP simplicity, let's query directly.
    
    # Verify requester is OWNER
    requester_membership = db.query(WorkspaceMembership).filter(
        WorkspaceMembership.user_id == current_user.id,
        WorkspaceMembership.workspace_id == workspace_id,
        WorkspaceMembership.role == RoleEnum.OWNER
    ).first()
    
    if not requester_membership:
        raise HTTPException(status_code=403, detail="Only OWNER can add members")
        
    # Find user to add
    user_to_add = db.query(User).filter(User.email == email).first()
    if not user_to_add:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Check if already member
    existing_member = db.query(WorkspaceMembership).filter(
        WorkspaceMembership.user_id == user_to_add.id,
        WorkspaceMembership.workspace_id == workspace_id
    ).first()
    
    if existing_member:
        raise HTTPException(status_code=400, detail="User already in workspace")
        
    new_membership = WorkspaceMembership(
        user_id=user_to_add.id,
        workspace_id=workspace_id,
        role=role
    )
    db.add(new_membership)
    db.commit()
    db.refresh(new_membership)
    
    return {
        "workspace_id": workspace_id,
        "name": requester_membership.workspace.name,
        "role": role
    }
