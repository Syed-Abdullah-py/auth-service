from pydantic import BaseModel, EmailStr
from typing import Optional, List
from enum import Enum

class RoleEnum(str, Enum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    DOCTOR = "DOCTOR"

# Token Schemas
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    user_id: Optional[int] = None
    email: Optional[str] = None

# User Schemas
class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: int

    class Config:
        from_attributes = True

# Workspace Schemas
class WorkspaceBase(BaseModel):
    name: str

class WorkspaceCreate(WorkspaceBase):
    pass

class WorkspaceResponse(WorkspaceBase):
    id: int
    role: RoleEnum

    class Config:
        from_attributes = True

# Membership Schemas
class MembershipResponse(BaseModel):
    workspace_id: int
    name: str
    role: RoleEnum
    
    class Config:
        from_attributes = True
