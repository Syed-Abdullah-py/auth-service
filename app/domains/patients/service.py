from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_bus import WorkspaceEvent, event_bus
from app.dependencies.rbac import WorkspaceContext
from app.models.patient import Patient
from app.domains.patients.schemas import PatientCreate, PatientUpdate


async def list_patients(db: AsyncSession, ctx: WorkspaceContext) -> list[Patient]:
    result = await db.execute(
        select(Patient).where(Patient.workspace_id == ctx.workspace_id)
    )
    return result.scalars().all()


async def create_patient(
    db: AsyncSession, payload: PatientCreate, ctx: WorkspaceContext
) -> Patient:
    patient = Patient(
        workspace_id=ctx.workspace_id,
        first_name=payload.first_name,
        last_name=payload.last_name,
        dob=payload.dob,
        gender=payload.gender,
        phone_number=payload.phone_number,
        mrn=payload.mrn,
        cnic=payload.cnic,
        address=payload.address,
        city=payload.city,
    )
    db.add(patient)
    await db.commit()
    await db.refresh(patient)

    await event_bus.publish(
        WorkspaceEvent(
            type="patient.created",
            workspace_id=ctx.workspace_id,
            payload={"patient_id": patient.id},
        )
    )
    return patient


async def get_patient(
    db: AsyncSession, patient_id: str, ctx: WorkspaceContext
) -> Patient:
    result = await db.execute(
        select(Patient).where(
            Patient.id == patient_id,
            Patient.workspace_id == ctx.workspace_id,
        )
    )
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")
    return patient


async def update_patient(
    db: AsyncSession, patient_id: str, payload: PatientUpdate, ctx: WorkspaceContext
) -> Patient:
    patient = await get_patient(db, patient_id, ctx)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(patient, field, value)

    await db.commit()
    await db.refresh(patient)
    return patient


async def delete_patient(
    db: AsyncSession, patient_id: str, ctx: WorkspaceContext
) -> None:
    patient = await get_patient(db, patient_id, ctx)
    await db.delete(patient)
    await db.commit()