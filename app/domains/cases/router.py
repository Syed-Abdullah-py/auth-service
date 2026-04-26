import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import MRI_SCANS_DIR
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


@router.post("/scan", status_code=200)
async def upload_scan(
    session_id: str = Form(...),
    file_index: int = Form(...),
    scan: UploadFile = File(...),
    ctx: WorkspaceContext = Depends(
        require_workspace_role(WorkspaceRoleEnum.ADMIN, WorkspaceRoleEnum.OWNER)
    ),
):
    await service.upload_scan_to_session(
        session_id=session_id,
        file_index=file_index,
        scan=scan,
        workspace_id=ctx.workspace_id,
    )
    return {"ok": True}


@router.post("/from-session", response_model=CaseResponse, status_code=201)
async def create_case_from_session(
    session_id: str = Form(...),
    patient_id: str = Form(...),
    priority: CasePriorityEnum = Form(CasePriorityEnum.NORMAL),
    assigned_to_member_id: str | None = Form(None),
    notes: str | None = Form(None),
    ctx: WorkspaceContext = Depends(
        require_workspace_role(WorkspaceRoleEnum.ADMIN, WorkspaceRoleEnum.OWNER)
    ),
    db: AsyncSession = Depends(get_db),
):
    case = await service.create_case_from_session(
        db=db,
        ctx=ctx,
        session_id=session_id,
        patient_id=patient_id,
        priority=priority,
        assigned_to_member_id=assigned_to_member_id,
        notes=notes,
    )
    return CaseResponse.from_case(case)


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


@router.get("/{case_id}/scan/{scan_index}")
async def serve_scan(
    case_id: str,
    scan_index: int,
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
    try:
        refs = json.loads(case.file_references)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=500, detail="Malformed file_references.")
    if scan_index < 0 or scan_index >= len(refs):
        raise HTTPException(status_code=404, detail="Scan index out of range.")
    filename = Path(refs[scan_index]).name
    path = MRI_SCANS_DIR / case_id / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Scan file not found on disk.")
    return FileResponse(
        str(path),
        media_type="application/octet-stream",
        filename=filename,
        headers={"Cache-Control": "private, max-age=1800"},
    )


_VALID_MODALITIES = {"t1", "t1ce", "t2", "flair"}
_TOTAL_SLICES = 155


@router.get("/{case_id}/mesh")
async def serve_mesh(
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
    await service.get_case(db, case_id, ctx)
    path = MRI_SCANS_DIR / case_id / "mesh.glb"
    if not path.exists():
        raise HTTPException(status_code=404, detail="3D mesh not yet generated for this case.")
    return FileResponse(
        str(path),
        media_type="model/gltf-binary",
        filename="mesh.glb",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.get("/{case_id}/seg")
async def serve_seg(
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
    await service.get_case(db, case_id, ctx)
    path = MRI_SCANS_DIR / case_id / "seg.nii"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Segmentation mask not yet generated for this case.")
    return FileResponse(
        str(path),
        media_type="application/octet-stream",
        filename="seg.nii",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.get("/{case_id}/slices/{modality}/{index}")
async def serve_slice(
    case_id: str,
    modality: str,
    index: int,
    masked: bool = False,
    ctx: WorkspaceContext = Depends(
        require_workspace_role(
            WorkspaceRoleEnum.DOCTOR,
            WorkspaceRoleEnum.ADMIN,
            WorkspaceRoleEnum.OWNER,
        )
    ),
    db: AsyncSession = Depends(get_db),
):
    if modality not in _VALID_MODALITIES:
        raise HTTPException(status_code=400, detail=f"Invalid modality '{modality}'. Must be one of {_VALID_MODALITIES}.")
    if index < 0 or index >= _TOTAL_SLICES:
        raise HTTPException(status_code=400, detail=f"Slice index must be 0–{_TOTAL_SLICES - 1}.")
    await service.get_case(db, case_id, ctx)
    suffix = "_m" if masked else ""
    path = MRI_SCANS_DIR / case_id / "slices" / modality / f"{index:03d}{suffix}.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Slice not found.")
    return FileResponse(
        str(path),
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=86400"},
    )


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