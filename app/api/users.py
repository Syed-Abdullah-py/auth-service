from fastapi import APIRouter, Depends
from app.api.deps import require_role
from app.models.models import WorkspaceRoleEnum

router = APIRouter()

# Owner / Admin only
@router.post("/users")
async def create_user_protected(
    role: WorkspaceRoleEnum = Depends(require_role(WorkspaceRoleEnum.OWNER, WorkspaceRoleEnum.ADMIN))
):
    return {"message": "User created successfully", "performed_by_role": role}


