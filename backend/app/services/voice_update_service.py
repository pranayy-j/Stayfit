import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.models import User
from app.repositories.voice_update_repository import VoiceUpdateRepository
from app.workflows.voice_update_graph import (
    RESUME_NODE,
    MissingDetail,
    VoiceUpdateContext,
    voice_update_graph,
)

logger = logging.getLogger(__name__)


class NeedsDetailError(Exception):
    """An eating update Claude could not fully understand; nothing was stored."""

    def __init__(self, missing: list[MissingDetail], items: list[str]) -> None:
        super().__init__(f"needs detail: {', '.join(missing)}")
        self.missing = missing
        self.items = items


@dataclass(frozen=True)
class VoiceUpdateResult:
    id: uuid.UUID
    created_at: datetime
    is_eating_update: bool
    eating_status: Literal["accepted"] | None


def _thread(voice_update_id: uuid.UUID) -> RunnableConfig:
    return {"configurable": {"thread_id": str(voice_update_id)}}


async def _forget(voice_update_id: uuid.UUID) -> None:
    """Drop the run's checkpoints from memory."""
    await voice_update_graph.checkpointer.adelete_thread(str(voice_update_id))


class VoiceUpdateService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def process(
        self, user: User, transcript: str, client_timestamp: datetime
    ) -> VoiceUpdateResult:
        """Run the voice-update pipeline up to the pause and commit.

        An accepted eating update is left paused for log_food_items to finish. Raises
        ClassificationError (JEV), ExtractionError (Claude) or NeedsDetailError; nothing is
        stored then.
        """
        voice_update_id = uuid.uuid4()
        paused = False
        try:
            state = await voice_update_graph.ainvoke(
                {
                    "voice_update_id": voice_update_id,
                    "user_id": user.id,
                    "timezone": user.timezone,
                    "transcript": transcript,
                    "client_timestamp": client_timestamp,
                },
                _thread(voice_update_id),
                context=VoiceUpdateContext(db=self.db),
            )
            if state["eating_status"] == "needs_detail":
                # The graph stopped before staging anything, so there is nothing to roll back.
                raise NeedsDetailError(state["missing_details"], state["unclear_items"])
            await self.db.commit()
            paused = state["eating_status"] == "accepted"
        finally:
            if not paused:
                await _forget(voice_update_id)
        return VoiceUpdateResult(
            id=voice_update_id,
            created_at=state["voice_update_created_at"],
            is_eating_update=state["is_eating_update"],
            eating_status=state["eating_status"],
        )

    async def log_food_items(self, voice_update_id: uuid.UUID) -> None:
        """Resume a paused run: look up or estimate nutrition and store the eating log.

        Sets food_logging_status to done, or failed on any error; never raises.
        """
        config = _thread(voice_update_id)
        repo = VoiceUpdateRepository(self.db)
        try:
            snapshot = await voice_update_graph.aget_state(config)
            if RESUME_NODE not in snapshot.next:
                raise LookupError("no paused run for this voice update")
            await voice_update_graph.ainvoke(None, config, context=VoiceUpdateContext(db=self.db))
            await repo.set_food_logging_status(voice_update_id, "done")
            await self.db.commit()
        except Exception as e:
            # Runs after the response, so nothing else would see this error. Log the type only:
            # DB and API error messages can carry food names, which are user content.
            logger.error(
                "Food logging failed for voice update %s: %s", voice_update_id, type(e).__name__
            )
            await self.db.rollback()
            await repo.set_food_logging_status(voice_update_id, "failed")
            await self.db.commit()
        finally:
            await _forget(voice_update_id)


async def log_food_items_in_background(voice_update_id: uuid.UUID) -> None:
    """Background-task entry point. The request's session is closed by now, so open a new one."""
    async with AsyncSessionLocal() as db:
        await VoiceUpdateService(db).log_food_items(voice_update_id)
