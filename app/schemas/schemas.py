from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Any
from datetime import datetime
from enum import Enum

# Enums
class GlobalRoleEnum(str, Enum):
    ADMIN = "ADMIN"
    RADIOLOGIST = "RADIOLOGIST"

class WorkspaceRoleEnum(str, Enum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    DOCTOR = "DOCTOR"

# Token Schemas
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    user_id: Optional[str] = None
    email: Optional[str] = None

# User Schemas
class UserBase(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    
class UserCreate(UserBase):
    password: str
    global_role: Optional[GlobalRoleEnum] = None

class UserUpdate(BaseModel):
    name: Optional[str] = None
    medical_license_id: Optional[str] = None
    avatar_url: Optional[str] = None
    cnic: Optional[str] = None
    phone_number: Optional[str] = None
    city: Optional[str] = None
    gender: Optional[str] = None

class UserResponse(UserBase):
    id: str
    global_role: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

# Workspace Schemas
class WorkspaceBase(BaseModel):
    name: str

class WorkspaceCreate(WorkspaceBase):
    slug: Optional[str] = None

class WorkspaceResponse(WorkspaceBase):
    id: str
    slug: str
    owner_id: str
    created_at: datetime

    class Config:
        from_attributes = True

# Membership Schemas
class MembershipResponse(BaseModel):
    id: str
    workspace_id: str
    role: WorkspaceRoleEnum
    joined_at: datetime
    workspace_name: Optional[str] = None # Enriched field
    
    class Config:
        from_attributes = True

# Patient Schemas
class PatientBase(BaseModel):
    first_name: str
    last_name: str
    dob: datetime
    gender: str
    phone_number: str
    mrn: Optional[str] = None
    cnic: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None

class PatientCreate(PatientBase):
    pass

class PatientResponse(PatientBase):
    id: str
    workspace_id: str
    created_at: datetime
    
    class Config:
        from_attributes = True

# Case Schemas
class CaseBase(BaseModel):
    status: str = "PENDING"
    priority: str = "normal"
    file_references: str # JSON string
    notes: Optional[str] = None

class CaseCreate(CaseBase):
    patient_id: str

class CaseResponse(CaseBase):
    id: str
    patient_id: str
    assigned_to_member_id: Optional[str] = None
    verdict: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True
