from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, VoiceUpdate
from app.workflows.voice_update_graph import (
    EatingStatus,
    FoodItem,
    VoiceUpdateContext,
    voice_update_graph,
)


@dataclass(frozen=True)
class VoiceUpdateResult:
    voice_update: VoiceUpdate
    eating_status: EatingStatus | None
    food_items: list[FoodItem]


class VoiceUpdateService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def process(
        self, user: User, transcript: str, client_timestamp: datetime
    ) -> VoiceUpdateResult:
        """Run the voice-update pipeline and commit.

        Raises ClassificationError (JEV) or ExtractionError (Claude); nothing is stored then.
        """
        state = await voice_update_graph.ainvoke(
            {
                "user_id": user.id,
                "timezone": user.timezone,
                "transcript": transcript,
                "client_timestamp": client_timestamp,
            },
            context=VoiceUpdateContext(db=self.db),
        )
        await self.db.commit()
        return VoiceUpdateResult(
            voice_update=state["voice_update"],
            eating_status=state["eating_status"],
            food_items=state["food_items"],
        )
