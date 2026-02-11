from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta

from app.core.security import verify_password, create_access_token, get_password_hash
from app.models.models import User, PendingUser
from app.schemas.schemas import UserCreate, UserResponse, Token, VerifyOtpRequest, ResendOtpRequest
from app.api.deps import get_db

router = APIRouter()

import random

@router.post("/register", response_model=UserResponse)
def register(user: UserCreate, db: Session = Depends(get_db)):
    # 1. Check if user already exists in main User table
    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = get_password_hash(user.password)
    
    # Generate 6-digit OTP
    otp = str(random.randint(100000, 999999))
    print(f"[Auth-Service] Generated OTP for {user.email}: {otp}")
    
    # 2. Check/Update PendingUser
    pending_user = db.query(PendingUser).filter(PendingUser.email == user.email).first()
    if pending_user:
        pending_user.hashed_password = hashed_password
        pending_user.name = user.name
        pending_user.global_role = user.global_role
        pending_user.verification_otp = otp
    else:
        pending_user = PendingUser(
            email=user.email,
            hashed_password=hashed_password,
            name=user.name,
            global_role=user.global_role,
            verification_otp=otp
        )
        db.add(pending_user)
    
    db.commit()
    db.refresh(pending_user)
    
    # Return a dummy UserResponse or similar, since we don't have a real User yet.
    # UserResponse expects 'id', 'is_verified', etc.
    # We can return the pending user data mapped to UserResponse
    return UserResponse(
        id=pending_user.id,
        email=pending_user.email,
        name=pending_user.name,
        global_role=pending_user.global_role,
        is_verified=False,
        created_at=pending_user.created_at,
        avatar_url=None
    )

@router.post("/verify-otp", response_model=Token)
def verify_otp(request: VerifyOtpRequest, db: Session = Depends(get_db)):
    # 1. Check PendingUser
    pending_user = db.query(PendingUser).filter(PendingUser.email == request.email).first()
    if not pending_user:
        raise HTTPException(status_code=404, detail="Registration session not found or expired.")
        
    if pending_user.verification_otp != request.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")
        
    # 2. Move to User Table
    new_user = User(
        email=pending_user.email,
        hashed_password=pending_user.hashed_password,
        name=pending_user.name,
        global_role=pending_user.global_role,
        is_verified=True, # Verified!
        verification_otp=None
    )
    db.add(new_user)
    
    # 3. Delete PendingUser
    db.delete(pending_user)
    db.commit()
    db.refresh(new_user)
    
    # Auto-login: Generate Token
    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={
            "sub": new_user.id, 
            "email": new_user.email,
            "global_role": new_user.global_role
        }, 
        expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/resend-otp")
def resend_otp(request: ResendOtpRequest, db: Session = Depends(get_db)):
    # Check PendingUser first
    pending_user = db.query(PendingUser).filter(PendingUser.email == request.email).first()
    
    if pending_user:
        otp = str(random.randint(100000, 999999))
        print(f"[Auth-Service] Resent OTP for {pending_user.email}: {otp}")
        pending_user.verification_otp = otp
        db.commit()
        return {"message": "OTP resent successfully"}
        
    # If not in pending, maybe they are already verified?
    user = db.query(User).filter(User.email == request.email).first()
    if user:
         raise HTTPException(status_code=400, detail="User already verified")
         
    raise HTTPException(status_code=404, detail="User not found")

@router.post("/login", response_model=Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # OAuth2PasswordRequestForm uses 'username' field, but we treat it as email
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # No need to check is_verified here because unverified users are not in this table anymore.
    
    access_token_expires = timedelta(minutes=30)
    
    # Debug: Print first 10 chars of SECRET_KEY
    from app.core.security import SECRET_KEY
    print(f"[Auth-Service] Using SECRET_KEY: {SECRET_KEY[:10]}...")
    
    access_token = create_access_token(
        data={
            "sub": user.id, 
            "email": user.email,
            "global_role": user.global_role
        }, 
        expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}
