from datetime import date, datetime
from pydantic import BaseModel


class PatientCreate(BaseModel):
    first_name: str
    last_name: str
    dob: date
    gender: str
    phone_number: str
    mrn: str | None = None
    cnic: str | None = None
    address: str | None = None
    city: str | None = None


class PatientUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    dob: date | None = None
    gender: str | None = None
    phone_number: str | None = None
    mrn: str | None = None
    cnic: str | None = None
    address: str | None = None
    city: str | None = None


class PatientResponse(BaseModel):
    id: str
    workspace_id: str
    first_name: str
    last_name: str
    dob: date
    gender: str
    phone_number: str
    mrn: str | None = None
    cnic: str | None = None
    address: str | None = None
    city: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True