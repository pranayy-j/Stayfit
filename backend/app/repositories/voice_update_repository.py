from sqlalchemy.ext.asyncio import AsyncSession

from app.models import VoiceUpdate


class VoiceUpdateRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def add(self, voice_update: VoiceUpdate) -> VoiceUpdate:
        """Stage a new voice update and flush so DB defaults and constraints apply now."""
        self.db.add(voice_update)
        await self.db.flush()
        return voice_update
