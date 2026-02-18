from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import re

from datetime import datetime, timedelta
import uuid

from app.models.models import User, Workspace, WorkspaceMember, WorkspaceRoleEnum, Invitation, JoinRequest, Case
from app.schemas.schemas import WorkspaceCreate, WorkspaceResponse, MembershipResponse, WorkspaceUpdate, InvitationCreate, InvitationResponse, JoinRequestCreate, JoinRequestResponse, JoinRequestApprove
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
    # 1. Check Global Admin Role
    # Workspaces can only be created by Administrators (Owner or Admin)
    if current_user.global_role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Only Global Administrators can create workspaces"
        )

    # 2. Generate Slug
    base_slug = create_slug(workspace.name)
    slug = base_slug
    counter = 1
    while db.query(Workspace).filter(Workspace.slug == slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1
        
    # 3. Create Workspace
    db_workspace = Workspace(name=workspace.name, slug=slug, owner_id=current_user.id)
    db.add(db_workspace)
    db.commit()
    db.refresh(db_workspace)
    
    # 4. Add creator as OWNER
    membership = WorkspaceMember(
        user_id=current_user.id,
        workspace_id=db_workspace.id,
        role=WorkspaceRoleEnum.OWNER
    )
    db.add(membership)
    db.commit()
    
    return db_workspace

@router.put("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
def update_workspace(
    workspace_id: str,
    workspace_update: WorkspaceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 1. Verify Verification: Only OWNER checks
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Check if current user is the owner (creator) OR has OWNER role in membership
    # The requirement says "Only the owner of a workspace can edit its name"
    # Checking membership role is better for transfer of ownership scenarios
    
    membership = db.query(WorkspaceMember).filter(
        WorkspaceMember.user_id == current_user.id,
        WorkspaceMember.workspace_id == workspace_id,
        WorkspaceMember.role == WorkspaceRoleEnum.OWNER
    ).first()

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Only the Workspace Owner can edit the workspace"
        )

    # 2. Update
    if workspace_update.name:
        workspace.name = workspace_update.name
        # Optionally update slug? Let's keep slug stable for now unless requested.
    
    db.commit()
    db.refresh(workspace)
    return workspace

@router.delete("/workspaces/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workspace(
    workspace_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 1. Verify Verification: Only OWNER checks
    membership = db.query(WorkspaceMember).filter(
        WorkspaceMember.user_id == current_user.id,
        WorkspaceMember.workspace_id == workspace_id,
        WorkspaceMember.role == WorkspaceRoleEnum.OWNER
    ).first()

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Only the Workspace Owner can delete the workspace"
        )

    # 2. Delete (Cascade should handle members if configured, mostly manual here to be safe)
    # SQLAlchemy cascade="all, delete" on relationship is preferred.
    # Assuming cascade is set up in checks. If not, we might need to delete members first.
    # Let's delete the workspace directly first.
    
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if workspace:
        db.delete(workspace)
        db.commit()
    
    return None

@router.post("/workspaces/{workspace_id}/members", response_model=MembershipResponse)
def add_member(
    workspace_id: str,
    email: str,
    role: WorkspaceRoleEnum,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Verify permission: Admin or Owner can add members
    requester_membership = db.query(WorkspaceMember).filter(
        WorkspaceMember.user_id == current_user.id,
        WorkspaceMember.workspace_id == workspace_id
    ).first()
    
    if not requester_membership or requester_membership.role not in [WorkspaceRoleEnum.OWNER, WorkspaceRoleEnum.ADMIN]:
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

@router.delete("/workspaces/{workspace_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    workspace_id: str,
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Find the requester's membership
    requester_membership = db.query(WorkspaceMember).filter(
        WorkspaceMember.user_id == current_user.id,
        WorkspaceMember.workspace_id == workspace_id
    ).first()
    
    if not requester_membership:
        raise HTTPException(status_code=403, detail="Not a member of this workspace")

    is_self_removal = current_user.id == user_id

    # If removing someone else, require OWNER or ADMIN role
    if not is_self_removal:
        if requester_membership.role not in [WorkspaceRoleEnum.OWNER, WorkspaceRoleEnum.ADMIN]:
            raise HTTPException(status_code=403, detail="Only OWNER or ADMIN can remove members")
    
    target_membership = db.query(WorkspaceMember).filter(
        WorkspaceMember.user_id == user_id,
        WorkspaceMember.workspace_id == workspace_id
    ).first()
    
    if not target_membership:
        raise HTTPException(status_code=404, detail="Member not found")
        
    # Owners cannot be removed (including by themselves — to prevent orphaned workspaces)
    if target_membership.role == WorkspaceRoleEnum.OWNER:
         raise HTTPException(status_code=403, detail="Cannot remove the Workspace Owner. Transfer ownership first.")
         
    # If requester is ADMIN, they cannot remove another ADMIN
    if not is_self_removal and requester_membership.role == WorkspaceRoleEnum.ADMIN and target_membership.role == WorkspaceRoleEnum.ADMIN:
         raise HTTPException(status_code=403, detail="Admins cannot remove other Admins")

    # 2. Perform Removal
    print(f"[Auth] Removing member {user_id} from workspace {workspace_id}")
    
    # Unassign any cases assigned to this member to avoid FK constraint issues
    db.query(Case).filter(Case.assigned_to_member_id == target_membership.id).update({"assigned_to_member_id": None})
    
    db.delete(target_membership)
    db.commit()
    
    return None

@router.get("/workspaces/{workspace_id}/members", response_model=List[MembershipResponse])
def get_workspace_members(
    workspace_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Verify membership (any member can see other members?)
    # Usually yes.
    requester = db.query(WorkspaceMember).filter(
        WorkspaceMember.user_id == current_user.id,
        WorkspaceMember.workspace_id == workspace_id
    ).first()
    
    if not requester:
        raise HTTPException(status_code=403, detail="Not a member of this workspace")
        
    members = db.query(WorkspaceMember).filter(
        WorkspaceMember.workspace_id == workspace_id
    ).all()
    
    results = []
    for m in members:
        results.append({
            "id": m.id,
            "workspace_id": m.workspace_id,
            "role": m.role,
            "joined_at": m.joined_at,
            "user": m.user, # Pydantic will serialize this using UserResponse
            "workspace_name": m.workspace.name
        })
    return results

# --- Invitation Endpoints ---

@router.post("/workspaces/{workspace_id}/invitations", response_model=InvitationResponse)
def create_invitation(
    workspace_id: str,
    invitation_in: InvitationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 1. Verify Permission
    requester_membership = db.query(WorkspaceMember).filter(
        WorkspaceMember.user_id == current_user.id,
        WorkspaceMember.workspace_id == workspace_id
    ).first()
    
    if not requester_membership or requester_membership.role not in [WorkspaceRoleEnum.OWNER, WorkspaceRoleEnum.ADMIN]:
        raise HTTPException(status_code=403, detail="Only OWNER or ADMIN can send invitations")

    # 2. Check if user is already a member
    # Find user by email (if exists)
    existing_user = db.query(User).filter(User.email == invitation_in.email).first()
    if existing_user:
        is_member = db.query(WorkspaceMember).filter(
            WorkspaceMember.user_id == existing_user.id,
            WorkspaceMember.workspace_id == workspace_id
        ).first()
        if is_member:
             raise HTTPException(status_code=400, detail="User is already a member of this workspace")

    # 3. Check for existing pending invitation
    existing_invite = db.query(Invitation).filter(
        Invitation.email == invitation_in.email,
        Invitation.workspace_id == workspace_id
    ).first()
    
    if existing_invite:
        # Refresh it
        existing_invite.expires_at = datetime.utcnow() + timedelta(days=7)
        existing_invite.token = str(uuid.uuid4())
        db.commit()
        db.refresh(existing_invite)
        return existing_invite

    # 4. Create Invitation
    token = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(days=7)
    
    # Role in DB is technically required by model but not used for logic anymore.
    # We can default it to DOCTOR or something harmless, or the model definition might need change if we want it nullable.
    # For now, let's default to DOCTOR to satisfy DB constraint if it exists.
    
    db_invitation = Invitation(
        email=invitation_in.email,
        role=WorkspaceRoleEnum.DOCTOR, # Placeholder, actual role derived on acceptance
        token=token,
        expires_at=expires_at,
        workspace_id=workspace_id
    )
    db.add(db_invitation)
    db.commit()
    db.refresh(db_invitation)
    
    return db_invitation

@router.get("/workspaces/{workspace_id}/invitations", response_model=List[InvitationResponse])
def get_workspace_invitations(
    workspace_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Verify permission
    requester_membership = db.query(WorkspaceMember).filter(
        WorkspaceMember.user_id == current_user.id,
        WorkspaceMember.workspace_id == workspace_id
    ).first()
    
    if not requester_membership or requester_membership.role not in [WorkspaceRoleEnum.OWNER, WorkspaceRoleEnum.ADMIN]:
         raise HTTPException(status_code=403, detail="Only OWNER or ADMIN can view invitations")

    invitations = db.query(Invitation).filter(Invitation.workspace_id == workspace_id).all()
    return invitations

@router.get("/invitations", response_model=List[InvitationResponse])
def get_my_invitations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Find invitations matching user's email
    invitations = db.query(Invitation).filter(
        Invitation.email == current_user.email
    ).all()
    
    # Enrich with workspace name
    for inv in invitations:
        inv.workspace_name = inv.workspace.name
        
    return invitations

@router.post("/invitations/{invitation_id}/accept", status_code=status.HTTP_200_OK)
def accept_invitation(
    invitation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    invitation = db.query(Invitation).filter(Invitation.id == invitation_id).first()
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")
        
    # Case-insensitive comparison
    if invitation.email.lower() != current_user.email.lower():
        print(f"Invitation email mismatch: {invitation.email} vs {current_user.email}")
        raise HTTPException(status_code=403, detail="Invitation does not belong to you")
        
    if invitation.expires_at < datetime.utcnow():
        db.delete(invitation)
        db.commit()
        raise HTTPException(status_code=400, detail="Invitation expired")
        
    # Check if already member (race condition safety)
    existing_member = db.query(WorkspaceMember).filter(
        WorkspaceMember.user_id == current_user.id,
        WorkspaceMember.workspace_id == invitation.workspace_id
    ).first()
    
    if existing_member:
        db.delete(invitation)
        db.commit()
        return {"message": "Already a member"}

    # Determine Role based on Global Role
    new_role = WorkspaceRoleEnum.DOCTOR
    if current_user.global_role == "ADMIN":
        new_role = WorkspaceRoleEnum.ADMIN

    # Add member
    new_membership = WorkspaceMember(
        user_id=current_user.id,
        workspace_id=invitation.workspace_id,
        role=new_role
    )
    db.add(new_membership)
    db.delete(invitation)
    db.commit()
    
    return {"message": "Invitation accepted"}

@router.post("/invitations/{invitation_id}/reject", status_code=status.HTTP_200_OK)
def reject_invitation(
    invitation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    invitation = db.query(Invitation).filter(Invitation.id == invitation_id).first()
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")

    if invitation.email != current_user.email:
         raise HTTPException(status_code=403, detail="Invitation does not belong to you")

    db.delete(invitation)
    db.commit()
    return {"message": "Invitation rejected"}

# --- Discovery & Join Endpoints ---

@router.get("/workspaces/discover", response_model=List[WorkspaceResponse])
def get_discoverable_workspaces(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Get IDs of workspaces user is already in
    user_workspace_ids = db.query(WorkspaceMember.workspace_id).filter(
        WorkspaceMember.user_id == current_user.id
    ).all()
    user_workspace_ids_list = [id for (id,) in user_workspace_ids]
    
    # Query workspaces NOT in that list
    query = db.query(Workspace)
    if user_workspace_ids_list:
        query = query.filter(Workspace.id.notin_(user_workspace_ids_list))
        
    workspaces = query.limit(20).all()
    return workspaces

@router.post("/workspaces/{workspace_id}/join-requests", response_model=JoinRequestResponse)
def create_join_request(
    workspace_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 1. Check if already member
    existing_member = db.query(WorkspaceMember).filter(
        WorkspaceMember.user_id == current_user.id,
        WorkspaceMember.workspace_id == workspace_id
    ).first()
    if existing_member:
        raise HTTPException(status_code=400, detail="Already a member of this workspace")
    
    # 2. Check for existing pending request
    existing_request = db.query(JoinRequest).filter(
        JoinRequest.user_id == current_user.id,
        JoinRequest.workspace_id == workspace_id,
        JoinRequest.status == "PENDING"
    ).first()
    if existing_request:
        return existing_request
    
    # 3. Create request
    db_request = JoinRequest(
        user_id=current_user.id,
        workspace_id=workspace_id,
        status="PENDING"
    )
    db.add(db_request)
    db.commit()
    db.refresh(db_request)
    return db_request

@router.get("/workspaces/{workspace_id}/join-requests", response_model=List[JoinRequestResponse])
def get_workspace_join_requests(
    workspace_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Verify permission (Admin/Owner)
    membership = db.query(WorkspaceMember).filter(
        WorkspaceMember.user_id == current_user.id,
        WorkspaceMember.workspace_id == workspace_id
    ).first()
    if not membership or membership.role not in [WorkspaceRoleEnum.OWNER, WorkspaceRoleEnum.ADMIN]:
        raise HTTPException(status_code=403, detail="Only Owner or Admin can view join requests")
    
    requests = db.query(JoinRequest).filter(
        JoinRequest.workspace_id == workspace_id,
        JoinRequest.status == "PENDING"
    ).all()
    
    # Enrich with workspace name
    for r in requests:
        r.workspace_name = r.workspace.name
        
    return requests

@router.post("/join-requests/{request_id}/approve", status_code=status.HTTP_200_OK)
def approve_join_request(
    request_id: str,
    approval_data: JoinRequestApprove,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 1. Find request
    request = db.query(JoinRequest).filter(JoinRequest.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Join request not found")
    
    # 2. Verify permission on THAT workspace
    membership = db.query(WorkspaceMember).filter(
        WorkspaceMember.user_id == current_user.id,
        WorkspaceMember.workspace_id == request.workspace_id
    ).first()
    if not membership or membership.role not in [WorkspaceRoleEnum.OWNER, WorkspaceRoleEnum.ADMIN]:
        raise HTTPException(status_code=403, detail="Only Owner or Admin can approve join requests")
    
    # 3. Approve
    request.status = "APPROVED"
    
    # 4. Determine Role based on Global Role
    # Fetch the user joining
    joining_user = db.query(User).filter(User.id == request.user_id).first()
    if not joining_user:
         raise HTTPException(status_code=404, detail="User not found")
         
    new_role = WorkspaceRoleEnum.DOCTOR
    if joining_user.global_role == "ADMIN":
        new_role = WorkspaceRoleEnum.ADMIN
    
    # 4. Add Member
    new_member = WorkspaceMember(
        user_id=request.user_id,
        workspace_id=request.workspace_id,
        role=new_role
    )
    db.add(new_member)
    db.commit()
    return {"message": "Request approved"}

@router.post("/join-requests/{request_id}/reject", status_code=status.HTTP_200_OK)
def reject_join_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 1. Find request
    request = db.query(JoinRequest).filter(JoinRequest.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Join request not found")
    
    # 2. Verify permission
    membership = db.query(WorkspaceMember).filter(
        WorkspaceMember.user_id == current_user.id,
        WorkspaceMember.workspace_id == request.workspace_id
    ).first()
    if not membership or membership.role not in [WorkspaceRoleEnum.OWNER, WorkspaceRoleEnum.ADMIN]:
        raise HTTPException(status_code=403, detail="Only Owner or Admin can reject join requests")
    
    # 3. Reject
    request.status = "REJECTED"
    db.commit()
    return {"message": "Request rejected"}
