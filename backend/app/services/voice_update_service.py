from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, VoiceUpdate
from app.workflows.voice_update_graph import (
    FoodItem,
    MissingDetail,
    VoiceUpdateContext,
    voice_update_graph,
)


class NeedsDetailError(Exception):
    """An eating update Claude could not fully understand; nothing was stored."""

    def __init__(self, missing: list[MissingDetail], items: list[str]) -> None:
        super().__init__(f"needs detail: {', '.join(missing)}")
        self.missing = missing
        self.items = items


@dataclass(frozen=True)
class VoiceUpdateResult:
    voice_update: VoiceUpdate
    eating_status: Literal["logged"] | None
    food_items: list[FoodItem]


class VoiceUpdateService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def process(
        self, user: User, transcript: str, client_timestamp: datetime
    ) -> VoiceUpdateResult:
        """Run the voice-update pipeline and commit.

        Raises ClassificationError (JEV), ExtractionError (Claude) or NeedsDetailError;
        nothing is stored then.
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
        if state["eating_status"] == "needs_detail":
            # The graph stopped before staging anything, so there is nothing to roll back.
            raise NeedsDetailError(state["missing_details"], state["unclear_items"])
        await self.db.commit()
        return VoiceUpdateResult(
            voice_update=state["voice_update"],
            eating_status=state["eating_status"],
            food_items=state["food_items"],
        )
