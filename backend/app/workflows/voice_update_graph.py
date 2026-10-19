"""LangGraph pipeline for a voice update: classify the transcript, then store it.

Each node does one step and returns only the state keys it owns. Add later steps (e.g. food
extraction for eating updates) as new nodes, with conditional edges on `is_eating_update`.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import NotRequired, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import VoiceUpdate
from app.repositories.voice_update_repository import VoiceUpdateRepository
from app.services import eating_classifier


class VoiceUpdateState(TypedDict):
    # Inputs
    user_id: uuid.UUID
    timezone: str
    transcript: str
    client_timestamp: datetime
    # Filled in by nodes
    is_eating_update: NotRequired[bool]
    voice_update: NotRequired[VoiceUpdate]


@dataclass(frozen=True)
class VoiceUpdateContext:
    """Per-request dependencies; kept out of state so state stays plain data."""

    db: AsyncSession


async def classify_transcript(state: VoiceUpdateState) -> dict:
    return {"is_eating_update": await eating_classifier.is_eating_update(state["transcript"])}


async def save_voice_update(state: VoiceUpdateState, runtime: Runtime[VoiceUpdateContext]) -> dict:
    # Stages the row only; the caller owns the transaction and commits.
    voice_update = await VoiceUpdateRepository(runtime.context.db).add(
        VoiceUpdate(
            user_id=state["user_id"],
            client_timestamp=state["client_timestamp"],
            timezone=state["timezone"],
            transcript=state["transcript"],
            is_eating_update=state["is_eating_update"],
        )
    )
    return {"voice_update": voice_update}


def build_voice_update_graph():
    graph = StateGraph(VoiceUpdateState, context_schema=VoiceUpdateContext)
    graph.add_node(classify_transcript)
    graph.add_node(save_voice_update)
    # Classify before touching the DB so no connection is held during the slow JEV call.
    graph.add_edge(START, "classify_transcript")
    graph.add_edge("classify_transcript", "save_voice_update")
    graph.add_edge("save_voice_update", END)
    return graph.compile()


# Compiled once; stateless and safe to share across concurrent requests.
voice_update_graph = build_voice_update_graph()
