from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import User
from app.repositories.user_repository import UserRepository
from app.services.google_auth import verify_google_id_token
from app.services.token_service import create_access_token, decode_access_token


@dataclass
class LoginResult:
    access_token: str
    user: User
    is_new_user: bool


def _valid_timezone(tz: str | None) -> str:
    if tz:
        try:
            ZoneInfo(tz)
            return tz
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return "UTC"


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)

    def login_with_google(self, google_id_token: str, timezone: str | None) -> LoginResult:
        """Verify a Google ID token, creating the user on first login. Raises InvalidGoogleToken."""
        claims = verify_google_id_token(google_id_token)
        email = claims["email"].lower()

        user = self.users.get_by_email(email)
        is_new_user = user is None
        if is_new_user:
            try:
                user = self.users.add(
                    User(
                        name=claims.get("name") or email.split("@")[0],
                        email=email,
                        timezone=_valid_timezone(timezone),
                    )
                )
                self.db.commit()
            except IntegrityError:
                # Another request created this user concurrently.
                self.db.rollback()
                user = self.users.get_by_email(email)
                is_new_user = False
            else:
                self.db.refresh(user)

        return LoginResult(create_access_token(user.id), user, is_new_user)

    def user_from_access_token(self, token: str) -> User | None:
        user_id = decode_access_token(token)
        return self.users.get_by_id(user_id) if user_id else None
