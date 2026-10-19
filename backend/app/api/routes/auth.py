import uuid
from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.auth.google import InvalidGoogleToken, verify_google_id_token
from app.auth.tokens import create_access_token
from app.db import get_db
from app.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class GoogleLoginRequest(BaseModel):
    id_token: str
    timezone: str | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    timezone: str
    created_at: datetime


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
    is_new_user: bool


def _valid_timezone(tz: str | None) -> str:
    if tz:
        try:
            ZoneInfo(tz)
            return tz
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return "UTC"


@router.post("/google", response_model=LoginResponse)
def login_with_google(body: GoogleLoginRequest, db: Annotated[Session, Depends(get_db)]):
    try:
        claims = verify_google_id_token(body.id_token)
    except InvalidGoogleToken as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid Google token: {e}") from e

    email = claims["email"].lower()
    user = db.scalar(select(User).where(User.email == email))
    is_new_user = user is None
    if is_new_user:
        user = User(
            name=claims.get("name") or email.split("@")[0],
            email=email,
            timezone=_valid_timezone(body.timezone),
        )
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            # Another request created this user concurrently.
            db.rollback()
            user = db.scalar(select(User).where(User.email == email))
            is_new_user = False
        else:
            db.refresh(user)

    return LoginResponse(
        access_token=create_access_token(user.id),
        user=UserOut.model_validate(user),
        is_new_user=is_new_user,
    )


@router.get("/me", response_model=UserOut)
def me(user: Annotated[User, Depends(get_current_user)]):
    return user
