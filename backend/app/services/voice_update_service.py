from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, VoiceUpdate
from app.repositories.voice_update_repository import VoiceUpdateRepository
from app.services import eating_classifier


class VoiceUpdateService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.voice_updates = VoiceUpdateRepository(db)

    async def process(self, user: User, transcript: str, client_timestamp: datetime) -> VoiceUpdate:
        """Classify the transcript with JEV, then store it. Raises TypeSafeError if JEV fails."""
        # Classify before touching the DB so no connection is held during the slow JEV call.
        is_eating_update = await eating_classifier.is_eating_update(transcript)

        voice_update = await self.voice_updates.add(
            VoiceUpdate(
                user_id=user.id,
                client_timestamp=client_timestamp,
                timezone=user.timezone,
                transcript=transcript,
                is_eating_update=is_eating_update,
            )
        )
        await self.db.commit()
        return voice_update
