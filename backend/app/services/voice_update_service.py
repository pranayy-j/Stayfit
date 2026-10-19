from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, VoiceUpdate
from app.workflows.voice_update_graph import VoiceUpdateContext, voice_update_graph


class VoiceUpdateService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def process(self, user: User, transcript: str, client_timestamp: datetime) -> VoiceUpdate:
        """Run the voice-update pipeline and commit. Raises ClassificationError if JEV fails."""
        result = await voice_update_graph.ainvoke(
            {
                "user_id": user.id,
                "timezone": user.timezone,
                "transcript": transcript,
                "client_timestamp": client_timestamp,
            },
            context=VoiceUpdateContext(db=self.db),
        )
        await self.db.commit()
        return result["voice_update"]
