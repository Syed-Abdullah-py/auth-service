from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies.db import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.domains.auth import service
from app.domains.auth.schemas import (
    RegisterRequest,
    RegisterResponse,
    VerifyOtpRequest,
    ResendOtpRequest,
    LoginRequest,
    TokenResponse,
    MessageResponse,
)

router = APIRouter(tags=["auth"])


@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    return await service.register(db, payload)


@router.post("/verify-otp", response_model=TokenResponse)
async def verify_otp(payload: VerifyOtpRequest, db: AsyncSession = Depends(get_db)):
    return await service.verify_otp(db, payload)


@router.post("/resend-otp", response_model=MessageResponse)
async def resend_otp(payload: ResendOtpRequest, db: AsyncSession = Depends(get_db)):
    return await service.resend_otp(db, payload.email)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    return await service.login(db, payload.email, payload.password)


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "global_role": current_user.global_role,
        "avatar_url": current_user.avatar_url,
        "is_verified": current_user.is_verified,
    }