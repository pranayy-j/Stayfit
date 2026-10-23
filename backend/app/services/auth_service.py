import asyncio
import hmac
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import AuthSession, User
from app.repositories.auth_session_repository import AuthSessionRepository
from app.repositories.user_repository import UserRepository
from app.services.google_auth import verify_google_id_token
from app.services.token_service import (
    create_access_token,
    decode_access_token,
    format_refresh_token,
    hash_refresh_secret,
    new_refresh_secret,
    parse_refresh_token,
)

logger = logging.getLogger(__name__)

# Two refreshes racing (e.g. two browser tabs) both send the same token; the loser shouldn't
# sign the user out. An old token seen after this long is treated as stolen.
REUSE_GRACE = timedelta(seconds=60)


class InvalidRefreshToken(Exception):
    """The refresh token is malformed, unknown, expired, revoked or already used."""


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str


@dataclass
class LoginResult:
    tokens: TokenPair
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
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.sessions = AuthSessionRepository(db)

    async def login_with_google(self, google_id_token: str, timezone: str | None) -> LoginResult:
        """Verify a Google ID token, creating the user on first login, and start a session.

        Raises InvalidGoogleToken.
        """
        # Google's check is a blocking HTTP call. It runs before any query, so no DB connection
        # is held while it waits.
        claims = await asyncio.to_thread(verify_google_id_token, google_id_token)
        email = claims["email"].lower()

        user = await self.users.get_by_email(email)
        is_new_user = user is None
        if is_new_user:
            try:
                user = await self.users.add(
                    User(
                        name=claims.get("name") or email.split("@")[0],
                        email=email,
                        timezone=_valid_timezone(timezone),
                    )
                )
            except IntegrityError:
                # Another request created this user concurrently.
                await self.db.rollback()
                user = await self.users.get_by_email(email)
                is_new_user = False

        tokens = await self._start_session(user.id)
        await self.db.commit()
        return LoginResult(tokens, user, is_new_user)

    async def refresh(self, refresh_token: str) -> TokenPair:
        """Swap a refresh token for a new pair and push the session's expiry forward.

        Raises InvalidRefreshToken. An old token used again after REUSE_GRACE revokes the session.
        """
        parsed = parse_refresh_token(refresh_token)
        if parsed is None:
            raise InvalidRefreshToken
        session_id, secret = parsed
        now = datetime.now(UTC)

        session = await self.sessions.get_by_id(session_id)
        if session is None or session.revoked_at is not None or session.expires_at <= now:
            raise InvalidRefreshToken

        presented = hash_refresh_secret(secret)
        if not hmac.compare_digest(presented, session.token_hash):
            if self._is_stale_reuse(session, presented, now):
                await self.sessions.revoke(session.id, now)
                await self.db.commit()
                logger.warning("Refresh token reused; revoked session %s", session.id)
            raise InvalidRefreshToken

        new_secret = new_refresh_secret()
        rotated = await self.sessions.rotate(
            session.id,
            old_hash=presented,
            new_hash=hash_refresh_secret(new_secret),
            rotated_at=now,
            expires_at=now + timedelta(days=settings.refresh_token_inactivity_days),
        )
        if not rotated:
            # A concurrent refresh with the same token won.
            raise InvalidRefreshToken
        await self.db.commit()
        return TokenPair(
            create_access_token(session.user_id), format_refresh_token(session.id, new_secret)
        )

    async def logout(self, refresh_token: str) -> None:
        """Revoke the session the refresh token belongs to. Unknown tokens are ignored."""
        parsed = parse_refresh_token(refresh_token)
        if parsed is None:
            return
        session_id, secret = parsed
        session = await self.sessions.get_by_id(session_id)
        presented = hash_refresh_secret(secret)
        hashes = (session.token_hash, session.previous_token_hash) if session else ()
        if any(h and hmac.compare_digest(presented, h) for h in hashes):
            await self.sessions.revoke(session.id, datetime.now(UTC))
            await self.db.commit()

    async def user_from_access_token(self, token: str) -> User | None:
        user_id = decode_access_token(token)
        if user_id is None:
            return None
        user = await self.users.get_by_id(user_id)
        # End the read transaction so the connection goes back to the pool before the route's
        # own work (e.g. slow AI calls).
        await self.db.commit()
        return user

    async def _start_session(self, user_id: uuid.UUID) -> TokenPair:
        secret = new_refresh_secret()
        session = await self.sessions.add(
            AuthSession(
                user_id=user_id,
                token_hash=hash_refresh_secret(secret),
                expires_at=datetime.now(UTC)
                + timedelta(days=settings.refresh_token_inactivity_days),
            )
        )
        return TokenPair(create_access_token(user_id), format_refresh_token(session.id, secret))

    @staticmethod
    def _is_stale_reuse(session: AuthSession, presented: str, now: datetime) -> bool:
        """True if `presented` is the token the last refresh replaced, outside the grace window."""
        return (
            session.previous_token_hash is not None
            and session.rotated_at is not None
            and hmac.compare_digest(presented, session.previous_token_hash)
            and now - session.rotated_at > REUSE_GRACE
        )
