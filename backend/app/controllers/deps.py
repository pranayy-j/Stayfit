from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.controllers.auth_cookies import ACCESS_COOKIE, is_web_client
from app.db import get_async_db
from app.models import User
from app.services.auth_service import AuthService

bearer = HTTPBearer(auto_error=False)


def get_auth_service(db: Annotated[AsyncSession, Depends(get_async_db)]) -> AuthService:
    return AuthService(db)


async def get_current_user(
    request: Request,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    # Native: Authorization header. Web: httpOnly cookie, only with the X-Client header.
    if creds:
        token = creds.credentials
    elif is_web_client(request):
        token = request.cookies.get(ACCESS_COOKIE)
    else:
        token = None
    user = await auth.user_from_access_token(token) if token else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return user
