from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.db import get_db
from app.dependencies.rbac import WorkspaceContext, require_workspace_role
from app.domains.cases import service
from app.domains.cases.schemas import (
    CaseResponse,
    CaseStatsResponse,
    CaseUpdate,
)
from app.models.case import CasePriorityEnum
from app.models.workspace import WorkspaceRoleEnum

router = APIRouter(tags=["cases"])


@router.get("/stats", response_model=CaseStatsResponse)
async def get_stats(
    response: Response,
    ctx: WorkspaceContext = Depends(
        require_workspace_role(
            WorkspaceRoleEnum.DOCTOR,
            WorkspaceRoleEnum.ADMIN,
            WorkspaceRoleEnum.OWNER,
        )
    ),
    db: AsyncSession = Depends(get_db),
):
    response.headers["Cache-Control"] = "private, max-age=30, stale-while-revalidate=300"
    return await service.get_stats(db, ctx)


@router.get("/recent", response_model=list[CaseResponse])
async def get_recent(
    response: Response,
    ctx: WorkspaceContext = Depends(
        require_workspace_role(
            WorkspaceRoleEnum.DOCTOR,
            WorkspaceRoleEnum.ADMIN,
            WorkspaceRoleEnum.OWNER,
        )
    ),
    db: AsyncSession = Depends(get_db),
):
    response.headers["Cache-Control"] = "private, max-age=30, stale-while-revalidate=300"
    cases = await service.get_recent(db, ctx)
    return [CaseResponse.from_case(c) for c in cases]


@router.get("/", response_model=list[CaseResponse])
async def list_cases(
    response: Response,
    ctx: WorkspaceContext = Depends(
        require_workspace_role(
            WorkspaceRoleEnum.DOCTOR,
            WorkspaceRoleEnum.ADMIN,
            WorkspaceRoleEnum.OWNER,
        )
    ),
    db: AsyncSession = Depends(get_db),
):
    response.headers["Cache-Control"] = "private, max-age=30, stale-while-revalidate=300"
    cases = await service.list_cases(db, ctx)
    return [CaseResponse.from_case(c) for c in cases]


@router.post("/", response_model=CaseResponse, status_code=201)
async def create_case(
    patient_id: str = Form(...),
    priority: CasePriorityEnum = Form(CasePriorityEnum.NORMAL),
    assigned_to_member_id: str | None = Form(None),
    notes: str | None = Form(None),
    scans: list[UploadFile] = File(..., description="Exactly 4 MRI scan files"),
    ctx: WorkspaceContext = Depends(
        require_workspace_role(WorkspaceRoleEnum.ADMIN, WorkspaceRoleEnum.OWNER)
    ),
    db: AsyncSession = Depends(get_db),
):
    case = await service.create_case(
        db=db,
        ctx=ctx,
        patient_id=patient_id,
        priority=priority,
        scans=scans,
        assigned_to_member_id=assigned_to_member_id,
        notes=notes,
    )
    return CaseResponse.from_case(case)


@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(
    case_id: str,
    ctx: WorkspaceContext = Depends(
        require_workspace_role(
            WorkspaceRoleEnum.DOCTOR,
            WorkspaceRoleEnum.ADMIN,
            WorkspaceRoleEnum.OWNER,
        )
    ),
    db: AsyncSession = Depends(get_db),
):
    case = await service.get_case(db, case_id, ctx)
    return CaseResponse.from_case(case)


@router.put("/{case_id}", response_model=CaseResponse)
async def update_case(
    case_id: str,
    payload: CaseUpdate,
    ctx: WorkspaceContext = Depends(
        require_workspace_role(
            WorkspaceRoleEnum.DOCTOR,
            WorkspaceRoleEnum.ADMIN,
            WorkspaceRoleEnum.OWNER,
        )
    ),
    db: AsyncSession = Depends(get_db),
):
    case = await service.update_case(db, case_id, payload, ctx)
    return CaseResponse.from_case(case)


@router.delete("/{case_id}", status_code=204)
async def delete_case(
    case_id: str,
    ctx: WorkspaceContext = Depends(
        require_workspace_role(WorkspaceRoleEnum.ADMIN, WorkspaceRoleEnum.OWNER)
    ),
    db: AsyncSession = Depends(get_db),
):
    await service.delete_case(db, case_id, ctx)