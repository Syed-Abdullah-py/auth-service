import json
import uuid
from datetime import datetime
from pathlib import Path

from async_lru import alru_cache
from fastapi import HTTPException, UploadFile
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_bus import WorkspaceEvent, event_bus
from app.core.pipeline import run_case_pipeline
from app.core.storage import MRI_SCANS_DIR, delete_scan_dir, save_scan_locally, save_scan_to_session, move_session_to_case
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
        .options(joinedload(Case.patient), joinedload(Case.assigned_to_user))
        .join(Patient, Case.patient_id == Patient.id)
        .where(Case.id == case_id, Patient.workspace_id == ctx.workspace_id)
    )
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found.")
    return case


async def _resolve_assigned_user_id(
    db: AsyncSession, member_id: str, workspace_id: str
) -> str | None:
    result = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.id == member_id,
            WorkspaceMember.workspace_id == workspace_id,
        )
    )
    member = result.scalar_one_or_none()
    return member.user_id if member else None


async def upload_scan_to_session(
    session_id: str,
    file_index: int,
    scan: UploadFile,
    workspace_id: str,
) -> None:
    _validate_scan_filename(scan.filename)
    file_bytes = await scan.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"File {scan.filename} exceeds 500MB limit.")
    await save_scan_to_session(
        file_bytes=file_bytes,
        session_id=f"{workspace_id}_{session_id}",
        file_index=file_index,
        filename=scan.filename,
    )


async def create_case_from_session(
    db: AsyncSession,
    ctx: WorkspaceContext,
    session_id: str,
    patient_id: str,
    priority: CasePriorityEnum,
    assigned_to_member_id: str | None = None,
    notes: str | None = None,
) -> Case:
    result = await db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.workspace_id == ctx.workspace_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Patient not found in this workspace.")

    assigned_to_user_id: str | None = None
    if assigned_to_member_id:
        member_result = await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.id == assigned_to_member_id,
                WorkspaceMember.workspace_id == ctx.workspace_id,
            )
        )
        member = member_result.scalar_one_or_none()
        if not member:
            raise HTTPException(status_code=404, detail="Assigned member not found in this workspace.")
        assigned_to_user_id = member.user_id

    case_id = str(uuid.uuid4())
    full_session_id = f"{ctx.workspace_id}_{session_id}"
    scan_paths = await move_session_to_case(full_session_id, case_id)

    if len(scan_paths) != 4:
        raise HTTPException(
            status_code=400,
            detail=f"Session has {len(scan_paths)} scan(s); exactly 4 are required. Upload all files first.",
        )

    case = Case(
        id=case_id,
        patient_id=patient_id,
        file_references=json.dumps(scan_paths),
        priority=priority,
        assigned_to_member_id=assigned_to_member_id,
        assigned_to_user_id=assigned_to_user_id,
        notes=notes,
        status=CaseStatusEnum.PROCESSING,
    )
    db.add(case)
    await db.commit()
    await db.refresh(case)

    # Run ML pipeline synchronously before returning - rolls back on failure
    case_dir = MRI_SCANS_DIR / case_id
    abs_paths = [case_dir / Path(p).name for p in scan_paths]
    try:
        await run_case_pipeline(case_dir, abs_paths)
    except Exception as exc:
        await db.delete(case)
        await db.commit()
        await delete_scan_dir(case_id)
        raise HTTPException(
            status_code=500,
            detail=f"Case pipeline failed: {exc}. Please re-upload the scans.",
        ) from exc

    case.status = CaseStatusEnum.PENDING
    await db.commit()

    result = await db.execute(
        select(Case)
        .options(joinedload(Case.patient), joinedload(Case.assigned_to_user))
        .where(Case.id == case.id)
    )
    case = result.scalar_one()

    await event_bus.publish(
        WorkspaceEvent(
            type="case.created",
            workspace_id=ctx.workspace_id,
            payload={"case_id": case.id, "patient_id": case.patient_id},
        )
    )
    return case


async def list_cases(db: AsyncSession, ctx: WorkspaceContext) -> list[Case]:
    query = (
        select(Case)
        .options(joinedload(Case.patient), joinedload(Case.assigned_to_user))
        .join(Patient, Case.patient_id == Patient.id)
        .where(Patient.workspace_id == ctx.workspace_id)
    )
    if ctx.role == WorkspaceRoleEnum.DOCTOR:
        query = query.where(Case.assigned_to_user_id == ctx.user.id)

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

    # Validate assigned member and capture user_id for stable reference
    assigned_to_user_id: str | None = None
    if assigned_to_member_id:
        member_result = await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.id == assigned_to_member_id,
                WorkspaceMember.workspace_id == ctx.workspace_id,
            )
        )
        member = member_result.scalar_one_or_none()
        if not member:
            raise HTTPException(status_code=404, detail="Assigned member not found in this workspace.")
        assigned_to_user_id = member.user_id

    # Save scans to local disk at app/db/mri_scans/{case_id}/
    case_id = str(uuid.uuid4())
    scan_paths = []

    for i, scan in enumerate(scans):
        file_bytes = await scan.read()
        if len(file_bytes) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File {scan.filename} exceeds 500MB limit.",
            )

        ext = scan.filename[scan.filename.index("."):]
        filename = f"scan_{i}{ext}"

        path = await save_scan_locally(
            file_bytes=file_bytes,
            case_id=case_id,
            filename=filename,
        )
        scan_paths.append(path)

    # Create case record
    case = Case(
        id=case_id,
        patient_id=patient_id,
        file_references=json.dumps(scan_paths),
        priority=priority,
        assigned_to_member_id=assigned_to_member_id,
        assigned_to_user_id=assigned_to_user_id,
        notes=notes,
        status=CaseStatusEnum.PROCESSING,
    )
    db.add(case)
    await db.commit()
    await db.refresh(case)

    # Run ML pipeline synchronously before returning - rolls back on failure
    case_dir = MRI_SCANS_DIR / case_id
    abs_paths = [case_dir / Path(p).name for p in scan_paths]
    try:
        await run_case_pipeline(case_dir, abs_paths)
    except Exception as exc:
        await db.delete(case)
        await db.commit()
        await delete_scan_dir(case_id)
        raise HTTPException(
            status_code=500,
            detail=f"Case pipeline failed: {exc}. Please re-upload the scans.",
        ) from exc

    case.status = CaseStatusEnum.PENDING
    await db.commit()

    result = await db.execute(
        select(Case)
        .options(joinedload(Case.patient), joinedload(Case.assigned_to_user))
        .where(Case.id == case.id)
    )
    case = result.scalar_one()

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
    if ctx.role == WorkspaceRoleEnum.DOCTOR and case.assigned_to_user_id != ctx.user.id:
        raise HTTPException(status_code=403, detail="You are not assigned to this case.")
    return case


async def update_case(
    db: AsyncSession, case_id: str, payload: CaseUpdate, ctx: WorkspaceContext
) -> Case:
    case = await _get_case_scoped(db, case_id, ctx)

    if ctx.role == WorkspaceRoleEnum.DOCTOR:
        if case.assigned_to_user_id != ctx.user.id:
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

    # When re-assigning, also update the stable user reference
    if "assigned_to_member_id" in updates:
        new_member_id = updates["assigned_to_member_id"]
        if new_member_id:
            updates["assigned_to_user_id"] = await _resolve_assigned_user_id(
                db, new_member_id, ctx.workspace_id
            )
        else:
            updates["assigned_to_user_id"] = None

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
    await delete_scan_dir(case_id)


@alru_cache(maxsize=128, ttl=60)
async def get_stats(db: AsyncSession, ctx: WorkspaceContext) -> dict:
    base = (
        select(Case.status, func.count(Case.id))
        .join(Patient, Case.patient_id == Patient.id)
        .where(Patient.workspace_id == ctx.workspace_id)
    )
    if ctx.role == WorkspaceRoleEnum.DOCTOR:
        base = base.where(Case.assigned_to_user_id == ctx.user.id)

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
        .options(joinedload(Case.patient), joinedload(Case.assigned_to_user))
        .join(Patient, Case.patient_id == Patient.id)
        .where(Patient.workspace_id == ctx.workspace_id)
    )
    if ctx.role == WorkspaceRoleEnum.DOCTOR:
        query = query.where(Case.assigned_to_user_id == ctx.user.id)

    query = query.order_by(Case.created_at.desc()).limit(5)
    result = await db.execute(query)
    return result.scalars().all()