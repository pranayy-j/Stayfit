from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.config import settings
from app.controllers.auth_cookies import (
    REFRESH_COOKIE,
    clear_auth_cookies,
    is_web_client,
    set_auth_cookies,
)
from app.controllers.deps import get_auth_service, get_current_user
from app.models import User
from app.schemas.auth import (
    GoogleLoginRequest,
    LoginResponse,
    LogoutResponse,
    RefreshResponse,
    RefreshTokenRequest,
    TokenResponse,
)
from app.schemas.common import UNAUTHORIZED
from app.schemas.user import UserOut
from app.services.auth_service import AuthService, InvalidRefreshToken, TokenPair
from app.services.google_auth import InvalidGoogleToken

router = APIRouter(prefix="/auth", tags=["auth"])


def _deliver_tokens(
    request: Request, response: Response, tokens: TokenPair
) -> TokenResponse | None:
    """Web gets httpOnly cookies and no tokens in the body; native gets them in the body."""
    if is_web_client(request):
        set_auth_cookies(response, tokens)
        return None
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


def _refresh_token_from(request: Request, body: RefreshTokenRequest | None) -> str | None:
    if is_web_client(request):
        return request.cookies.get(REFRESH_COOKIE)
    return body.refresh_token if body else None


@router.post("/google", responses=UNAUTHORIZED)
async def login_with_google(
    body: GoogleLoginRequest,
    request: Request,
    response: Response,
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> LoginResponse:
    try:
        result = await auth.login_with_google(body.id_token, body.timezone)
    except InvalidGoogleToken as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid Google token: {e}") from e

    return LoginResponse(
        tokens=_deliver_tokens(request, response, result.tokens),
        user=UserOut.model_validate(result.user),
        is_new_user=result.is_new_user,
    )


@router.post(
    "/refresh",
    responses={401: {**UNAUTHORIZED[401], "description": "Refresh token invalid or expired"}},
)
async def refresh(
    request: Request,
    response: Response,
    auth: Annotated[AuthService, Depends(get_auth_service)],
    body: RefreshTokenRequest | None = None,
) -> RefreshResponse:
    token = _refresh_token_from(request, body)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing refresh token")
    try:
        tokens = await auth.refresh(token)
    except InvalidRefreshToken as e:
        # Cookies are left alone: in a race between tabs, the winner has just set new ones.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token") from e
    return RefreshResponse(tokens=_deliver_tokens(request, response, tokens))


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    auth: Annotated[AuthService, Depends(get_auth_service)],
    body: RefreshTokenRequest | None = None,
) -> LogoutResponse:
    token = _refresh_token_from(request, body)
    if token:
        await auth.logout(token)
    if is_web_client(request):
        clear_auth_cookies(response)
    return LogoutResponse()


@router.get("/me", responses=UNAUTHORIZED)
async def me(user: Annotated[User, Depends(get_current_user)]) -> UserOut:
    return UserOut.model_validate(user)
