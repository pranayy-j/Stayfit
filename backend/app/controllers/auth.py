from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.controllers.deps import get_auth_service, get_current_user
from app.models import User
from app.schemas.auth import GoogleLoginRequest, LoginResponse
from app.schemas.user import UserOut
from app.services.auth_service import AuthService
from app.services.google_auth import InvalidGoogleToken

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/google", response_model=LoginResponse)
def login_with_google(
    body: GoogleLoginRequest, auth: Annotated[AuthService, Depends(get_auth_service)]
):
    try:
        result = auth.login_with_google(body.id_token, body.timezone)
    except InvalidGoogleToken as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid Google token: {e}") from e

    return LoginResponse(
        access_token=result.access_token,
        user=UserOut.model_validate(result.user),
        is_new_user=result.is_new_user,
    )


@router.get("/me", response_model=UserOut)
def me(user: Annotated[User, Depends(get_current_user)]):
    return user
