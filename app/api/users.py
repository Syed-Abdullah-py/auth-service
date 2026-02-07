from fastapi import APIRouter, Depends
from app.api.deps import require_role
from app.models.models import RoleEnum

router = APIRouter()

# Owner / Admin only
@router.post("/users")
async def create_user_protected(
    role: RoleEnum = Depends(require_role(RoleEnum.OWNER, RoleEnum.ADMIN))
):
    return {"message": "User created successfully", "performed_by_role": role}

# Doctor allowed (and Owner/Admin as they are superusers? No, role list must be explicit usually, or hierarchical)
# Requirement said: OWNER, ADMIN, DOCTOR for list_patients
@router.get("/patients")
async def list_patients(
    role: RoleEnum = Depends(require_role(RoleEnum.OWNER, RoleEnum.ADMIN, RoleEnum.DOCTOR))
):
    return {"message": "List of patients", "performed_by_role": role}
