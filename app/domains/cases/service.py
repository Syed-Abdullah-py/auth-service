import json
import uuid
from datetime import datetime

from fastapi import HTTPException, UploadFile
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_bus import WorkspaceEvent, event_bus
from app.core.storage import upload_to_supabase
from app.dependencies.rbac import WorkspaceContext
from app.domains.cases.schemas import CaseUpdate
from app.models.case import Case, CaseStatusEnum, CasePriorityEnum
from app.models.patient import Patient
from app.models.workspace import WorkspaceMember, WorkspaceRoleEnum

ALLOWED_EXTENSIONS = {".nii", ".nii.gz", ".dcm", ".nrrd", ".mha", ".mhd", ".txt"}
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB per file


def _validate_scan_filename(filename: str) -> None:
    lower = filename.lower()
    if not any(lower.endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: {filename}. Allowed: {ALLOWED_EXTENSIONS}",
        )


async def _get_case_scoped(
    db: AsyncSession, case_id: str, ctx: WorkspaceContext
) -> Case:
    result = await db.execute(
        select(Case)
        .join(Patient, Case.patient_id == Patient.id)
        .where(Case.id == case_id, Patient.workspace_id == ctx.workspace_id)
    )
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found.")
    return case


async def list_cases(db: AsyncSession, ctx: WorkspaceContext) -> list[Case]:
    query = (
        select(Case)
        .join(Patient, Case.patient_id == Patient.id)
        .where(Patient.workspace_id == ctx.workspace_id)
    )
    if ctx.role == WorkspaceRoleEnum.DOCTOR:
        query = query.where(Case.assigned_to_member_id == ctx.member_id)

    result = await db.execute(query)
    return result.scalars().all()


async def create_case(
    db: AsyncSession,
    ctx: WorkspaceContext,
    patient_id: str,
    priority: CasePriorityEnum,
    scans: list[UploadFile],
    assigned_to_member_id: str | None = None,
    notes: str | None = None,
) -> Case:
    # Validate exactly 4 scans
    if len(scans) != 4:
        raise HTTPException(status_code=400, detail="Exactly 4 MRI scans are required.")

    for scan in scans:
        _validate_scan_filename(scan.filename)

    # Verify patient belongs to workspace
    result = await db.execute(
        select(Patient).where(
            Patient.id == patient_id,
            Patient.workspace_id == ctx.workspace_id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Patient not found in this workspace.")

    # Validate assigned member
    if assigned_to_member_id:
        member = await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.id == assigned_to_member_id,
                WorkspaceMember.workspace_id == ctx.workspace_id,
            )
        )
        if not member.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Assigned member not found in this workspace.")

    # Upload scans to Supabase Storage
    case_id = str(uuid.uuid4())
    scan_urls = []

    for i, scan in enumerate(scans):
        file_bytes = await scan.read()
        if len(file_bytes) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File {scan.filename} exceeds 500MB limit.",
            )

        ext = scan.filename[scan.filename.index("."):]
        file_path = f"{ctx.workspace_id}/{patient_id}/{case_id}/scan_{i}{ext}"

        url = await upload_to_supabase(
            file_bytes=file_bytes,
            file_path=file_path,
            content_type=scan.content_type or "application/octet-stream",
        )
        scan_urls.append(url)

    # Create case record
    case = Case(
        id=case_id,
        patient_id=patient_id,
        file_references=json.dumps(scan_urls),
        priority=priority,
        assigned_to_member_id=assigned_to_member_id,
        notes=notes,
    )
    db.add(case)
    await db.commit()
    await db.refresh(case)

    await event_bus.publish(
        WorkspaceEvent(
            type="case.created",
            workspace_id=ctx.workspace_id,
            payload={"case_id": case.id, "patient_id": case.patient_id},
        )
    )
    return case


async def get_case(
    db: AsyncSession, case_id: str, ctx: WorkspaceContext
) -> Case:
    case = await _get_case_scoped(db, case_id, ctx)
    if ctx.role == WorkspaceRoleEnum.DOCTOR and case.assigned_to_member_id != ctx.member_id:
        raise HTTPException(status_code=403, detail="You are not assigned to this case.")
    return case


async def update_case(
    db: AsyncSession, case_id: str, payload: CaseUpdate, ctx: WorkspaceContext
) -> Case:
    case = await _get_case_scoped(db, case_id, ctx)

    if ctx.role == WorkspaceRoleEnum.DOCTOR:
        if case.assigned_to_member_id != ctx.member_id:
            raise HTTPException(status_code=403, detail="You are not assigned to this case.")
        allowed = payload.model_dump(exclude_unset=True)
        forbidden = set(allowed.keys()) - {"verdict", "notes", "status"}
        if forbidden:
            raise HTTPException(
                status_code=403,
                detail=f"Doctors cannot update: {', '.join(forbidden)}",
            )

    updates = payload.model_dump(exclude_unset=True)
    if "verdict" in updates:
        updates["verdict_updated_at"] = datetime.utcnow()

    for field, value in updates.items():
        setattr(case, field, value)

    await db.commit()
    await db.refresh(case)

    await event_bus.publish(
        WorkspaceEvent(
            type="case.updated",
            workspace_id=ctx.workspace_id,
            payload={"case_id": case.id, "status": case.status},
        )
    )
    return case


async def delete_case(
    db: AsyncSession, case_id: str, ctx: WorkspaceContext
) -> None:
    case = await _get_case_scoped(db, case_id, ctx)
    await db.delete(case)
    await db.commit()


async def get_stats(db: AsyncSession, ctx: WorkspaceContext) -> dict:
    base = (
        select(Case.status, func.count(Case.id))
        .join(Patient, Case.patient_id == Patient.id)
        .where(Patient.workspace_id == ctx.workspace_id)
    )
    if ctx.role == WorkspaceRoleEnum.DOCTOR:
        base = base.where(Case.assigned_to_member_id == ctx.member_id)

    base = base.group_by(Case.status)
    result = await db.execute(base)
    rows = {row[0]: row[1] for row in result.all()}

    pending = rows.get(CaseStatusEnum.PENDING, 0)
    processing = rows.get(CaseStatusEnum.PROCESSING, 0)
    reviewed = rows.get(CaseStatusEnum.REVIEWED, 0)

    return {
        "total": pending + processing + reviewed,
        "pending": pending,
        "processing": processing,
        "reviewed": reviewed,
    }


async def get_recent(db: AsyncSession, ctx: WorkspaceContext) -> list[Case]:
    query = (
        select(Case)
        .join(Patient, Case.patient_id == Patient.id)
        .where(Patient.workspace_id == ctx.workspace_id)
    )
    if ctx.role == WorkspaceRoleEnum.DOCTOR:
        query = query.where(Case.assigned_to_member_id == ctx.member_id)

    query = query.order_by(Case.created_at.desc()).limit(5)
    result = await db.execute(query)
    return result.scalars().all()