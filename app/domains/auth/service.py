import logging
import random
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import get_password_hash, verify_password, create_access_token
from app.domains.auth.schemas import (
    RegisterRequest,
    RegisterResponse,
    VerifyOtpRequest,
    TokenResponse,
)
from app.models.user import User, PendingUser

logger = logging.getLogger(__name__)


def _generate_otp() -> str:
    return str(random.randint(100000, 999999))


def _send_otp(email: str, otp: str) -> None:
    logger.warning("[DEV ONLY] OTP for %s: %s", email, otp)


async def register(db: AsyncSession, payload: RegisterRequest) -> RegisterResponse:
    result = await db.execute(select(User).where(User.email == payload.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    hashed = get_password_hash(payload.password)
    otp = _generate_otp()

    result = await db.execute(
        select(PendingUser).where(PendingUser.email == payload.email)
    )
    pending = result.scalar_one_or_none()

    if pending:
        pending.hashed_password = hashed
        pending.name = payload.name
        pending.global_role = payload.global_role
        pending.verification_otp = otp
    else:
        pending = PendingUser(
            email=payload.email,
            hashed_password=hashed,
            name=payload.name,
            global_role=payload.global_role,
            verification_otp=otp,
        )
        db.add(pending)

    await db.commit()
    await db.refresh(pending)
    _send_otp(pending.email, otp)

    return RegisterResponse(
        id=pending.id,
        email=pending.email,
        name=pending.name,
        global_role=pending.global_role,
        message="Registration successful. Check your email for the OTP.",
    )


async def verify_otp(db: AsyncSession, payload: VerifyOtpRequest) -> TokenResponse:
    result = await db.execute(
        select(PendingUser).where(PendingUser.email == payload.email)
    )
    pending = result.scalar_one_or_none()

    if not pending:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pending registration found for this email.",
        )
    if pending.verification_otp != payload.otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP. Please try again.",
        )

    user = User(
        email=pending.email,
        hashed_password=pending.hashed_password,
        name=pending.name,
        global_role=pending.global_role,
        is_verified=True,
    )
    db.add(user)
    await db.delete(pending)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(
        data={"sub": user.id, "email": user.email, "global_role": user.global_role}
    )
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        email=user.email,
        name=user.name,
        global_role=user.global_role,
    )


async def resend_otp(db: AsyncSession, email: str) -> dict:
    result = await db.execute(select(PendingUser).where(PendingUser.email == email))
    pending = result.scalar_one_or_none()

    if not pending:
        result = await db.execute(select(User).where(User.email == email))
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This email is already verified. Please log in.",
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pending registration found for this email.",
        )

    otp = _generate_otp()
    pending.verification_otp = otp
    await db.commit()
    _send_otp(pending.email, otp)
    return {"message": "OTP resent successfully."}


async def login(db: AsyncSession, email: str, password: str) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account not verified. Please complete OTP verification.",
        )

    token = create_access_token(
        data={"sub": user.id, "email": user.email, "global_role": user.global_role}
    )
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        email=user.email,
        name=user.name,
        global_role=user.global_role,
    )