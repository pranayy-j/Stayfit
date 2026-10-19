from datetime import datetime

from sqlalchemy.orm import Session

from app.models import User


class VoiceUpdateService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def process(self, user: User, transcript: str, timestamp: datetime) -> None:
        # TODO: implement voice update handling.
        pass
