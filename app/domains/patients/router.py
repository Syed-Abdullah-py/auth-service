from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.db import get_db
from app.dependencies.rbac import WorkspaceContext, require_workspace_role
from app.domains.patients import service
from app.domains.patients.schemas import PatientCreate, PatientResponse, PatientUpdate
from app.models.workspace import WorkspaceRoleEnum

router = APIRouter(tags=["patients"])


@router.get("/", response_model=list[PatientResponse])
async def list_patients(
    ctx: WorkspaceContext = Depends(
        require_workspace_role(
            WorkspaceRoleEnum.DOCTOR,
            WorkspaceRoleEnum.ADMIN,
            WorkspaceRoleEnum.OWNER,
        )
    ),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_patients(db, ctx)


@router.post("/", response_model=PatientResponse, status_code=201)
async def create_patient(
    payload: PatientCreate,
    ctx: WorkspaceContext = Depends(
        require_workspace_role(WorkspaceRoleEnum.ADMIN, WorkspaceRoleEnum.OWNER)
    ),
    db: AsyncSession = Depends(get_db),
):
    return await service.create_patient(db, payload, ctx)


@router.get("/{patient_id}", response_model=PatientResponse)
async def get_patient(
    patient_id: str,
    ctx: WorkspaceContext = Depends(
        require_workspace_role(
            WorkspaceRoleEnum.DOCTOR,
            WorkspaceRoleEnum.ADMIN,
            WorkspaceRoleEnum.OWNER,
        )
    ),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_patient(db, patient_id, ctx)


@router.put("/{patient_id}", response_model=PatientResponse)
async def update_patient(
    patient_id: str,
    payload: PatientUpdate,
    ctx: WorkspaceContext = Depends(
        require_workspace_role(WorkspaceRoleEnum.ADMIN, WorkspaceRoleEnum.OWNER)
    ),
    db: AsyncSession = Depends(get_db),
):
    return await service.update_patient(db, patient_id, payload, ctx)


@router.delete("/{patient_id}", status_code=204)
async def delete_patient(
    patient_id: str,
    ctx: WorkspaceContext = Depends(
        require_workspace_role(WorkspaceRoleEnum.ADMIN, WorkspaceRoleEnum.OWNER)
    ),
    db: AsyncSession = Depends(get_db),
):
    await service.delete_patient(db, patient_id, ctx)