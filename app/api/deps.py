from typing import Generator, Optional
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.core.security import SECRET_KEY, ALGORITHM
from app.models.models import User, WorkspaceMember, WorkspaceRoleEnum
from app.schemas.schemas import TokenData

# Helper to get the database session
def get_db() -> Generator:
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        email: str = payload.get("email")
        if user_id is None:
            raise credentials_exception
        token_data = TokenData(user_id=user_id, email=email)
    except JWTError:
        raise credentials_exception
        
    user = db.query(User).filter(User.id == token_data.user_id).first()
    if user is None:
        raise credentials_exception
    return user

# Helper to get workspace_id from header
def get_workspace_id(
    x_workspace_id: Optional[str] = Header(None, alias="X-Workspace-Id")
) -> Optional[str]:
    if x_workspace_id:
        return x_workspace_id
    return None

# Helper to get workspace role
def get_workspace_role(
    user: User = Depends(get_current_user),
    workspace_id: Optional[str] = Depends(get_workspace_id),
    db: Session = Depends(get_db),
) -> WorkspaceRoleEnum:
    if not workspace_id:
         raise HTTPException(status_code=400, detail="X-Workspace-Id header is required")

    membership = db.query(WorkspaceMember).filter(
        WorkspaceMember.user_id == user.id,
        WorkspaceMember.workspace_id == workspace_id
    ).first()

    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this workspace")

    return membership.role

# Dependency factory for role requirements
def require_role(*allowed_roles: str):
    def checker(role: WorkspaceRoleEnum = Depends(get_workspace_role)):
        if role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return role
    return checker
