from pydantic import BaseModel

from app.schemas.user import UserOut


class GoogleLoginRequest(BaseModel):
    id_token: str
    timezone: str | None = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
    is_new_user: bool
