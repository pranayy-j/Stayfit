from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.user import UserOut


class GoogleLoginRequest(BaseModel):
    id_token: str
    timezone: str | None = None


class RefreshTokenRequest(BaseModel):
    """Native apps send the refresh token in the body. Web sends no body: it's in a cookie."""

    refresh_token: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Seconds until the access token expires.")


class LoginResponse(BaseModel):
    tokens: TokenResponse | None = Field(
        description="Native apps only. null for web, which gets the tokens as httpOnly cookies."
    )
    user: UserOut
    is_new_user: bool


class RefreshResponse(BaseModel):
    tokens: TokenResponse | None = Field(
        description="Native apps only. null for web, which gets the tokens as httpOnly cookies."
    )


class LogoutResponse(BaseModel):
    status: Literal["signed_out"] = "signed_out"
