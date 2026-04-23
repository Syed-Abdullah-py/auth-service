from pydantic import BaseModel, EmailStr, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    global_role: str = "RADIOLOGIST"

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return v

    @field_validator("global_role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in ("ADMIN", "RADIOLOGIST"):
            raise ValueError("global_role must be ADMIN or RADIOLOGIST.")
        return v


class RegisterResponse(BaseModel):
    id: str
    email: str
    name: str | None
    global_role: str | None
    message: str

    class Config:
        from_attributes = True


class VerifyOtpRequest(BaseModel):
    email: EmailStr
    otp: str


class ResendOtpRequest(BaseModel):
    email: EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    name: str | None
    global_role: str | None


class MessageResponse(BaseModel):
    message: str


class GoogleAuthRequest(BaseModel):
    id_token: str
    global_role: str | None = None

    @field_validator("global_role")
    @classmethod
    def validate_role(cls, v: str | None) -> str | None:
        if v is not None and v not in ("ADMIN", "RADIOLOGIST"):
            raise ValueError("global_role must be ADMIN or RADIOLOGIST.")
        return v