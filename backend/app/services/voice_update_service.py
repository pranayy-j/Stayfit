from datetime import datetime

from sqlalchemy.orm import Session

from app.models import User
from app.services import eating_classifier


class VoiceUpdateService:
    def __init__(self, db: Session) -> None:
        self.db = db

    async def process(self, user: User, transcript: str, timestamp: datetime) -> bool:
        """Return whether the transcript is an eating update. Nothing is persisted yet."""
        return await eating_classifier.is_eating_update(transcript)
