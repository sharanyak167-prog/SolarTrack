"""Authentication and Authorization module for SolarTrack.

Provides JWT generation, bcrypt password hashing, FastAPI dependencies for role-based
access control (admin / viewer), and user management.
"""
from datetime import datetime, timedelta, timezone
import os
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import db
from .models import User

# Configuration
def jwt_secret() -> str:
    key = os.getenv("JWT_SECRET_KEY", "")
    if len(key) < 32:
        raise RuntimeError("Set JWT_SECRET_KEY to a random value of at least 32 characters in .env")
    return key
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 12  # 12 hours

security_scheme = HTTPBearer(auto_error=False)


# Pydantic Schemas
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str
    full_name: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    full_name: Optional[str] = None
    role: str
    is_active: bool
    created_at: Optional[datetime] = None


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=60, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=12)
    full_name: Optional[str] = Field(default=None, max_length=100)
    role: str = "viewer"  # admin | viewer

    @field_validator("password")
    @classmethod
    def validate_password(cls, value):
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 UTF-8 bytes")
        return value


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, value):
        if value is not None and (len(value) < 12 or len(value.encode("utf-8")) > 72):
            raise ValueError("Password must be at least 12 characters and at most 72 UTF-8 bytes")
        return value


# Password utilities
def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, jwt_secret(), algorithms=[JWT_ALGORITHM])
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


def get_current_user(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Security(security_scheme),
    s: Session = Depends(db.get_session),
) -> User:
    """Resolve the authenticated user from a bearer token or same-site cookie."""
    token: Optional[str] = None
    if creds and creds.credentials:
        token = creds.credentials
    elif "access_token" in request.cookies:
        token = request.cookies.get("access_token")

    if token:
        payload = decode_token(token)
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="Malformed token payload")
        user = s.scalar(select(User).where(User.username == username))
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="User account is deactivated or does not exist")
        return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated. Please log in.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Enforce admin privileges."""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required for this action",
        )
    return user


def require_viewer_or_admin(user: User = Depends(get_current_user)) -> User:
    """Enforce authenticated viewer or admin."""
    if user.role not in ("admin", "viewer"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized role",
        )
    return user
