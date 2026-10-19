"""LangGraph pipeline for a voice update.

    START → classify_transcript ─┬─ eating ──→ extract_food_items ─┐
                                 └─ not eating ────────────────────┴→ save_voice_update → END

Each node does one step and returns only the state keys it owns.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, NotRequired, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import VoiceUpdate
from app.repositories.voice_update_repository import VoiceUpdateRepository
from app.services import eating_classifier, food_extractor
from app.services.meal_time import Meal, meal_at, resolve_consumed_at

EatingStatus = Literal["logged", "needs_detail"]


@dataclass(frozen=True)
class FoodItem:
    name: str
    everyday_quantity: float
    everyday_unit: str
    metric_quantity: float
    metric_unit: Literal["g", "l"]
    quantity_is_default: bool
    consumed_at: datetime
    meal: Meal


class VoiceUpdateState(TypedDict):
    # Inputs
    user_id: uuid.UUID
    timezone: str
    transcript: str
    client_timestamp: datetime
    # Filled in by nodes
    is_eating_update: NotRequired[bool]
    eating_status: NotRequired[EatingStatus | None]
    food_items: NotRequired[list[FoodItem]]
    voice_update: NotRequired[VoiceUpdate]


@dataclass(frozen=True)
class VoiceUpdateContext:
    """Per-request dependencies; kept out of state so state stays plain data."""

    db: AsyncSession


async def classify_transcript(state: VoiceUpdateState) -> dict:
    is_eating = await eating_classifier.is_eating_update(state["transcript"])
    return {"is_eating_update": is_eating, "eating_status": None, "food_items": []}


def route_after_classify(state: VoiceUpdateState) -> str:
    return "extract_food_items" if state["is_eating_update"] else "save_voice_update"


async def extract_food_items(state: VoiceUpdateState) -> dict:
    extracted = await food_extractor.extract_food_items(state["transcript"])
    if not extracted:
        # No specific food named: not an eating update, ask the user for detail.
        return {"is_eating_update": False, "eating_status": "needs_detail", "food_items": []}

    recorded_at = state["client_timestamp"]
    items = []
    for item in extracted:
        consumed_at = resolve_consumed_at(item.time, recorded_at)
        items.append(
            FoodItem(
                name=item.name,
                everyday_quantity=item.everyday_quantity,
                everyday_unit=item.everyday_unit,
                metric_quantity=item.metric_quantity,
                metric_unit=item.metric_unit,
                quantity_is_default=item.quantity_is_default,
                consumed_at=consumed_at,
                meal=item.time.meal or meal_at(consumed_at.time()),
            )
        )
    # TODO: temporary until food items are persisted; prints to the uvicorn terminal.
    for item in items:
        print(f"[food item] user={state['user_id']} {item}")
    return {"eating_status": "logged", "food_items": items}


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
    graph.add_node(extract_food_items)
    graph.add_node(save_voice_update)
    # All AI calls run before touching the DB, so no connection is held while waiting on them.
    graph.add_edge(START, "classify_transcript")
    graph.add_conditional_edges(
        "classify_transcript", route_after_classify, ["extract_food_items", "save_voice_update"]
    )
    graph.add_edge("extract_food_items", "save_voice_update")
    graph.add_edge("save_voice_update", END)
    return graph.compile()


# Compiled once; stateless and safe to share across concurrent requests.
voice_update_graph = build_voice_update_graph()
