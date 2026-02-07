from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import re

from app.models.models import User, Workspace, WorkspaceMember, WorkspaceRoleEnum
from app.schemas.schemas import WorkspaceCreate, WorkspaceResponse, MembershipResponse
from app.api.deps import get_db, get_current_user

router = APIRouter()

def create_slug(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s-]+', '-', slug)
    return slug

@router.get("/workspaces", response_model=List[MembershipResponse])
def get_my_workspaces(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Fetch memberships for the current user
    memberships = db.query(WorkspaceMember).filter(
        WorkspaceMember.user_id == current_user.id
    ).all()
    
    results = []
    for m in memberships:
        results.append({
            "id": m.id,
            "workspace_id": m.workspace_id,
            "role": m.role,
            "joined_at": m.joined_at,
            "workspace_name": m.workspace.name
        })
    return results

@router.post("/workspaces", response_model=WorkspaceResponse)
def create_workspace(
    workspace: WorkspaceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 1. Generate Slug
    base_slug = create_slug(workspace.name)
    slug = base_slug
    counter = 1
    while db.query(Workspace).filter(Workspace.slug == slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1
        
    # 2. Create Workspace
    db_workspace = Workspace(name=workspace.name, slug=slug, owner_id=current_user.id)
    db.add(db_workspace)
    db.commit()
    db.refresh(db_workspace)
    
    # 3. Add creator as OWNER
    membership = WorkspaceMember(
        user_id=current_user.id,
        workspace_id=db_workspace.id,
        role=WorkspaceRoleEnum.OWNER
    )
    db.add(membership)
    db.commit()
    
    return db_workspace

@router.post("/workspaces/{workspace_id}/members", response_model=MembershipResponse)
def add_member(
    workspace_id: str,
    email: str,
    role: WorkspaceRoleEnum,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Verify requester is OWNER
    requester_membership = db.query(WorkspaceMember).filter(
        WorkspaceMember.user_id == current_user.id,
        WorkspaceMember.workspace_id == workspace_id,
        WorkspaceMember.role == WorkspaceRoleEnum.OWNER
    ).first()
    
    if not requester_membership:
        requester_membership = db.query(WorkspaceMember).filter(
            WorkspaceMember.user_id == current_user.id,
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.role == WorkspaceRoleEnum.ADMIN
        ).first()
        # Allow ADMIN to add members too? Usually yes.
        if not requester_membership:
             raise HTTPException(status_code=403, detail="Only OWNER or ADMIN can add members")
        
    # Find user to add
    user_to_add = db.query(User).filter(User.email == email).first()
    if not user_to_add:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Check if already member
    existing_member = db.query(WorkspaceMember).filter(
        WorkspaceMember.user_id == user_to_add.id,
        WorkspaceMember.workspace_id == workspace_id
    ).first()
    
    if existing_member:
        raise HTTPException(status_code=400, detail="User already in workspace")
        
    new_membership = WorkspaceMember(
        user_id=user_to_add.id,
        workspace_id=workspace_id,
        role=role
    )
    db.add(new_membership)
    db.commit()
    db.refresh(new_membership)
    
    return {
        "id": new_membership.id,
        "workspace_id": workspace_id,
        "role": role,
        "joined_at": new_membership.joined_at,
        "workspace_name": requester_membership.workspace.name
    }
