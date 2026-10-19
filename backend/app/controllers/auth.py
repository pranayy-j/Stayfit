from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.controllers.deps import get_auth_service, get_current_user
from app.models import User
from app.schemas.auth import GoogleLoginRequest, LoginResponse
from app.schemas.common import UNAUTHORIZED
from app.schemas.user import UserOut
from app.services.auth_service import AuthService
from app.services.google_auth import InvalidGoogleToken

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/google", responses=UNAUTHORIZED)
def login_with_google(
    body: GoogleLoginRequest, auth: Annotated[AuthService, Depends(get_auth_service)]
) -> LoginResponse:
    try:
        result = auth.login_with_google(body.id_token, body.timezone)
    except InvalidGoogleToken as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid Google token: {e}") from e

    return LoginResponse(
        access_token=result.access_token,
        user=UserOut.model_validate(result.user),
        is_new_user=result.is_new_user,
    )


@router.get("/me", responses=UNAUTHORIZED)
def me(user: Annotated[User, Depends(get_current_user)]) -> UserOut:
    return UserOut.model_validate(user)
