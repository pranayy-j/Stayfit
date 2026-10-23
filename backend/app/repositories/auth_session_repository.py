import uuid
from datetime import datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuthSession


class AuthSessionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, session_id: uuid.UUID) -> AuthSession | None:
        return await self.db.get(AuthSession, session_id)

    async def add(self, session: AuthSession) -> AuthSession:
        """Stage a new session and flush so its ID and defaults are set now."""
        self.db.add(session)
        await self.db.flush()
        return session

    async def rotate(
        self,
        session_id: uuid.UUID,
        old_hash: str,
        new_hash: str,
        rotated_at: datetime,
        expires_at: datetime,
    ) -> bool:
        """Swap in a new token hash, only if `old_hash` is still current and not revoked.

        Returns False when another request rotated or revoked the session first.
        """
        result = await self.db.execute(
            update(AuthSession)
            .where(
                AuthSession.id == session_id,
                AuthSession.token_hash == old_hash,
                AuthSession.revoked_at.is_(None),
            )
            .values(
                token_hash=new_hash,
                previous_token_hash=old_hash,
                rotated_at=rotated_at,
                expires_at=expires_at,
            )
        )
        return result.rowcount == 1

    async def revoke(self, session_id: uuid.UUID, revoked_at: datetime) -> None:
        await self.db.execute(
            update(AuthSession)
            .where(AuthSession.id == session_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=revoked_at)
        )
