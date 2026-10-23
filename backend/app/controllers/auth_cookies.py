"""Auth cookies for the web app.

Web gets its tokens as httpOnly cookies so page scripts can't read them. Native apps keep
using the Authorization header and never get cookies.

The web app marks every request with `X-Client: web`, and cookies are only honoured on
requests that carry it. A custom header can't be added by another site without passing our
CORS allowlist, so this also blocks cross-site request forgery.
"""

from fastapi import Request, Response

from app.config import settings
from app.services.auth_service import TokenPair

ACCESS_COOKIE = "stayfit_access"
REFRESH_COOKIE = "stayfit_refresh"
# The refresh token is only sent to /auth/* (refresh and logout), not to every API call.
REFRESH_COOKIE_PATH = "/auth"


def is_web_client(request: Request) -> bool:
    return request.headers.get("X-Client") == "web"


def set_auth_cookies(response: Response, tokens: TokenPair) -> None:
    response.set_cookie(
        ACCESS_COOKIE,
        tokens.access_token,
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        tokens.refresh_token,
        max_age=settings.refresh_token_inactivity_days * 24 * 60 * 60,
        path=REFRESH_COOKIE_PATH,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(
        ACCESS_COOKIE, path="/", secure=settings.cookie_secure, httponly=True, samesite="lax"
    )
    response.delete_cookie(
        REFRESH_COOKIE,
        path=REFRESH_COOKIE_PATH,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )
