# app/domains/auth/service.py
import logging
import random
from fastapi import HTTPException, status
import time
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.security import (
    get_password_hash_async,
    verify_password_async,
    create_access_token,
)
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
    print(f"\n  *** OTP for {email}: {otp} ***\n", flush=True)


async def register(db: AsyncSession, payload: RegisterRequest) -> RegisterResponse:
    t0 = time.time()
    
    # 1. Check existing user
    t_start = time.time()
    result = await db.execute(select(User).where(User.email == payload.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )
    print(f"[DEBUG] DB Check existing user: {time.time() - t_start:.4f}s")

    # 2. Hash password
    t_start = time.time()
    hashed = await get_password_hash_async(payload.password)
    print(f"[DEBUG] Password Hashing: {time.time() - t_start:.4f}s")

    otp = _generate_otp()

    # 3. Check pending user
    t_start = time.time()
    result = await db.execute(
        select(PendingUser).where(PendingUser.email == payload.email)
    )
    pending = result.scalar_one_or_none()
    print(f"[DEBUG] DB Check pending user: {time.time() - t_start:.4f}s")

    t_start = time.time()
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

    # 4. Commit and Refresh
    await db.commit()
    await db.refresh(pending)
    print(f"[DEBUG] DB Commit & Refresh: {time.time() - t_start:.4f}s")
    
    _send_otp(pending.email, otp)

    print(f"[DEBUG] TOTAL Register Time: {time.time() - t0:.4f}s")
    return RegisterResponse(
        id=pending.id,
        email=pending.email,
        name=pending.name,
        global_role=pending.global_role,
        message="Registration successful. Check your email for the OTP.",
    )


async def verify_otp(db: AsyncSession, payload: VerifyOtpRequest) -> TokenResponse:
    import time
    t0 = time.time()
    
    t_start = time.time()
    result = await db.execute(
        select(PendingUser).where(PendingUser.email == payload.email)
    )
    pending = result.scalar_one_or_none()
    print(f"[DEBUG] verify_otp - DB Fetch: {time.time() - t_start:.4f}s")

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

    t_start = time.time()
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
    print(f"[DEBUG] verify_otp - DB Commit & Refresh: {time.time() - t_start:.4f}s")

    t_start = time.time()
    token = create_access_token(
        data={"sub": user.id, "email": user.email, "global_role": user.global_role}
    )
    print(f"[DEBUG] verify_otp - Token generation: {time.time() - t_start:.4f}s")
    
    print(f"[DEBUG] TOTAL verify_otp Time: {time.time() - t0:.4f}s")
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        email=user.email,
        name=user.name,
        global_role=user.global_role,
    )


async def resend_otp(db: AsyncSession, email: str) -> dict:
    import time
    t0 = time.time()
    
    t_start = time.time()
    result = await db.execute(select(PendingUser).where(PendingUser.email == email))
    pending = result.scalar_one_or_none()
    print(f"[DEBUG] resend_otp - DB Fetch Pending: {time.time() - t_start:.4f}s")

    if not pending:
        t_start = time.time()
        result = await db.execute(select(User).where(User.email == email))
        user_exists = result.scalar_one_or_none()
        print(f"[DEBUG] resend_otp - DB Fetch User: {time.time() - t_start:.4f}s")
        
        if user_exists:
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
    
    t_start = time.time()
    await db.commit()
    print(f"[DEBUG] resend_otp - DB Commit: {time.time() - t_start:.4f}s")
    
    _send_otp(pending.email, otp)
    print(f"[DEBUG] TOTAL resend_otp Time: {time.time() - t0:.4f}s")
    return {"message": "OTP resent successfully."}


async def login(db: AsyncSession, email: str, password: str) -> TokenResponse:
    import time
    t0 = time.time()
    
    t_start = time.time()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    print(f"[DEBUG] login - DB Fetch User: {time.time() - t_start:.4f}s")

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if user.hashed_password is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This account uses Google Sign-In. Please use the Google button to log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    t_start = time.time()
    is_valid = await verify_password_async(password, user.hashed_password)
    print(f"[DEBUG] login - Password Verification: {time.time() - t_start:.4f}s")
    
    if not is_valid:
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

    t_start = time.time()
    token = create_access_token(
        data={"sub": user.id, "email": user.email, "global_role": user.global_role}
    )
    print(f"[DEBUG] login - Token generation: {time.time() - t_start:.4f}s")
    
    print(f"[DEBUG] TOTAL login Time: {time.time() - t0:.4f}s")
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        email=user.email,
        name=user.name,
        global_role=user.global_role,
    )


async def google_auth(
    db: AsyncSession,
    id_token: str,
    global_role: str | None,
) -> TokenResponse:
    # 1. Verify the id_token with Google's tokeninfo endpoint
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": id_token},
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token.",
        )

    token_data = resp.json()

    # 2. Validate the token was issued for this app
    if settings.GOOGLE_CLIENT_ID and token_data.get("aud") != settings.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token audience mismatch.",
        )

    google_sub = token_data.get("sub")
    email = token_data.get("email")
    name = token_data.get("name")
    avatar_url = token_data.get("picture")

    if not google_sub or not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incomplete profile from Google.",
        )

    # 3. Look up by google_id (returning Google user - fastest path)
    result = await db.execute(select(User).where(User.google_id == google_sub))
    user = result.scalar_one_or_none()

    if user:
        if avatar_url and user.avatar_url != avatar_url:
            user.avatar_url = avatar_url
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

    # 4. Check if a password account exists with the same email - link it silently
    result = await db.execute(select(User).where(User.email == email))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        existing_user.google_id = google_sub
        if avatar_url and not existing_user.avatar_url:
            existing_user.avatar_url = avatar_url
        await db.commit()
        await db.refresh(existing_user)
        token = create_access_token(
            data={
                "sub": existing_user.id,
                "email": existing_user.email,
                "global_role": existing_user.global_role,
            }
        )
        return TokenResponse(
            access_token=token,
            user_id=existing_user.id,
            email=existing_user.email,
            name=existing_user.name,
            global_role=existing_user.global_role,
        )

    # 5. No account found - new signup requires a role
    if not global_role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="GOOGLE_USER_NOT_FOUND",
        )

    # 6. Create a new verified user (Google already confirmed the email)
    new_user = User(
        email=email,
        hashed_password=None,
        google_id=google_sub,
        name=name,
        global_role=global_role,
        avatar_url=avatar_url,
        is_verified=True,
        terms_accepted=True,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    token = create_access_token(
        data={"sub": new_user.id, "email": new_user.email, "global_role": new_user.global_role}
    )
    return TokenResponse(
        access_token=token,
        user_id=new_user.id,
        email=new_user.email,
        name=new_user.name,
        global_role=new_user.global_role,
    )