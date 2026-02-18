from pydantic import BaseModel, EmailStr, Field
from typing import Optional
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
    is_verified: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

class VerifyOtpRequest(BaseModel):
    email: EmailStr
    otp: str

class ResendOtpRequest(BaseModel):
    email: EmailStr

# Workspace Schemas
class WorkspaceBase(BaseModel):
    name: str

class WorkspaceCreate(WorkspaceBase):
    slug: Optional[str] = None

class WorkspaceUpdate(BaseModel):
    name: Optional[str] = None

class WorkspaceResponse(WorkspaceBase):
    id: str
    slug: str
    owner_id: str
    created_at: datetime

    class Config:
        from_attributes = True

# Membership Schemas
# Membership Schemas
class MembershipResponse(BaseModel):
    id: str
    workspace_id: str
    role: WorkspaceRoleEnum
    joined_at: datetime
    workspace_name: Optional[str] = None # Enriched field
    user: Optional[UserResponse] = None # Enriched field
    
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

class PatientUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    dob: Optional[datetime] = None
    gender: Optional[str] = None
    phone_number: Optional[str] = None
    mrn: Optional[str] = None
    cnic: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None

class PatientResponse(PatientBase):
    id: str
    workspace_id: str
    created_at: datetime
    updated_at: datetime
    
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
    assigned_to_member_id: Optional[str] = None

class CaseUpdate(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    file_references: Optional[str] = None
    notes: Optional[str] = None
    verdict: Optional[str] = None
    assigned_to_member_id: Optional[str] = None

class CaseResponse(CaseBase):
    id: str
    patient_id: str
    assigned_to_member_id: Optional[str] = None
    verdict: Optional[str] = None
    verdict_updated_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    patient: Optional[PatientResponse] = None
    
    class Config:
        from_attributes = True

# Invitation Schemas
class InvitationBase(BaseModel):
    email: EmailStr
    # role: WorkspaceRoleEnum  <-- Removed, derived from global role on acceptance


class InvitationCreate(InvitationBase):
    pass

class InvitationResponse(InvitationBase):
    id: str
    workspace_id: str
    token: str
    expires_at: datetime
    workspace_name: Optional[str] = None

    class Config:
        from_attributes = True

# Join Request Schemas
class JoinRequestBase(BaseModel):
    pass

class JoinRequestCreate(JoinRequestBase):
    workspace_id: str

class JoinRequestApprove(BaseModel):
    pass

class JoinRequestResponse(JoinRequestBase):
    id: str
    workspace_id: str
    user_id: str
    status: str
    created_at: datetime
    user: Optional[UserResponse] = None
    workspace_name: Optional[str] = None

    class Config:
        from_attributes = True
