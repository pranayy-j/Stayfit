"""LangGraph pipeline for a voice update.

    START → classify_transcript ─┬─ eating ──→ extract_food_items ─┬─ accepted ─────┐
                                 │                                 └─ needs_detail ─┼→ END
                                 └─ not eating ─────────────────────────────────────┴→ save

    save (save_voice_update) ─┬─ not eating → END
                              └─ accepted → ⏸ pause: the service commits and responds 200
                                            ↓ resumed by a background task
                                 lookup_foods ─┬─ all known ─────────────────────┐
                                               └─ new foods → estimate_nutrition ┴→ save_food_logs

An eating update is all or nothing: it is "accepted" only when Claude understood what, when and
how much for every item. Otherwise it is "needs_detail", no food item is kept and nothing is
saved.

The run pauses before lookup_foods so the response doesn't wait on the nutrition lookup and the
Claude estimate. The paused state lives in an in-memory checkpointer, keyed by the voice update
id as thread id, and holds only plain data (no ORM objects), since it outlives the request's DB
session.

Each node does one step and returns only the state keys it owns.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, NotRequired, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EatingTrackerEntry, VoiceUpdate
from app.repositories.calorie_chart_repository import CalorieChartRepository
from app.repositories.eating_tracker_repository import EatingTrackerRepository
from app.repositories.voice_update_repository import VoiceUpdateRepository
from app.services import eating_classifier, food_extractor, nutrition_estimator
from app.services.food_extractor import ExtractedFoodItem
from app.services.meal_time import Meal, meal_at, resolve_consumed_at
from app.services.nutrition import consumed_nutrition
from app.services.nutrition_estimator import FoodNutrition

EatingStatus = Literal["accepted", "needs_detail"]
MissingDetail = Literal["what", "when", "how_much"]

# The node the run pauses before; the background task resumes from here.
RESUME_NODE = "lookup_foods"


@dataclass(frozen=True)
class FoodItem:
    name: str  # as said, e.g. "rotia"
    canonical_name: str  # lowercase and singular, e.g. "roti"; the calorie_chart key
    everyday_quantity: float
    everyday_unit: str
    metric_quantity: float
    metric_unit: Literal["g", "ml"]
    quantity_is_default: bool
    consumed_at: datetime  # in the recording's own UTC offset
    meal: Meal


class VoiceUpdateState(TypedDict):
    # Inputs
    voice_update_id: uuid.UUID
    user_id: uuid.UUID
    timezone: str
    transcript: str
    client_timestamp: datetime
    # Filled in by nodes
    is_eating_update: NotRequired[bool]
    eating_status: NotRequired[EatingStatus | None]
    food_items: NotRequired[list[FoodItem]]
    missing_details: NotRequired[list[MissingDetail]]
    unclear_items: NotRequired[list[str]]
    voice_update_created_at: NotRequired[datetime]
    # Foods not in calorie_chart: {canonical name: everyday unit said}
    unknown_foods: NotRequired[dict[str, str]]
    estimates: NotRequired[dict[str, FoodNutrition]]


@dataclass(frozen=True)
class VoiceUpdateContext:
    """Per-request dependencies; kept out of state so state stays plain data."""

    db: AsyncSession


async def classify_transcript(state: VoiceUpdateState) -> dict:
    is_eating = await eating_classifier.is_eating_update(state["transcript"])
    return {
        "is_eating_update": is_eating,
        "eating_status": None,
        "food_items": [],
        "missing_details": [],
        "unclear_items": [],
    }


def route_after_classify(state: VoiceUpdateState) -> str:
    return "extract_food_items" if state["is_eating_update"] else "save_voice_update"


async def extract_food_items(state: VoiceUpdateState) -> dict:
    extracted = await food_extractor.extract_food_items(state["transcript"])
    missing = _missing_details(extracted)
    if missing:
        # All or nothing: one unclear item means no item is kept.
        return {
            "eating_status": "needs_detail",
            "missing_details": missing,
            "unclear_items": [item.name for item in extracted if _is_unclear(item)],
        }

    recorded_at = state["client_timestamp"]
    items = []
    for item in extracted:
        consumed_at = resolve_consumed_at(item.time, recorded_at)
        is_litres = item.metric_unit == "l"
        items.append(
            FoodItem(
                name=item.name,
                canonical_name=" ".join(item.canonical_name.lower().split()),
                everyday_quantity=item.everyday_quantity,
                everyday_unit=item.everyday_unit,
                metric_quantity=item.metric_quantity * 1000 if is_litres else item.metric_quantity,
                metric_unit="ml" if is_litres else "g",
                quantity_is_default=item.quantity_is_default,
                consumed_at=consumed_at,
                meal=item.time.meal or meal_at(consumed_at.time()),
            )
        )
    return {"eating_status": "accepted", "food_items": items}


def _is_unclear(item: ExtractedFoodItem) -> bool:
    return not (item.food_recognized and item.time_understood and item.quantity_understood)


def _missing_details(extracted: list[ExtractedFoodItem]) -> list[MissingDetail]:
    """Which of what / when / how much Claude could not understand for any item."""
    missing: list[MissingDetail] = []
    if not extracted or not all(item.food_recognized for item in extracted):
        missing.append("what")
    if not all(item.time_understood for item in extracted):
        missing.append("when")
    if not all(item.quantity_understood for item in extracted):
        missing.append("how_much")
    return missing


def route_after_extract(state: VoiceUpdateState) -> str:
    # needs_detail saves nothing for now; the client asks the user and sends a new update.
    return END if state.get("eating_status") == "needs_detail" else "save_voice_update"


async def save_voice_update(state: VoiceUpdateState, runtime: Runtime[VoiceUpdateContext]) -> dict:
    # Stages the row only; the caller owns the transaction and commits.
    accepted = state["eating_status"] == "accepted"
    voice_update = await VoiceUpdateRepository(runtime.context.db).add(
        VoiceUpdate(
            id=state["voice_update_id"],
            user_id=state["user_id"],
            client_timestamp=state["client_timestamp"],
            timezone=state["timezone"],
            transcript=state["transcript"],
            is_eating_update=state["is_eating_update"],
            food_logging_status="pending" if accepted else None,
        )
    )
    return {"voice_update_created_at": voice_update.created_at}


def route_after_save(state: VoiceUpdateState) -> str:
    return RESUME_NODE if state["eating_status"] == "accepted" else END


async def lookup_foods(state: VoiceUpdateState, runtime: Runtime[VoiceUpdateContext]) -> dict:
    db = runtime.context.db
    units = {item.canonical_name: item.everyday_unit for item in state["food_items"]}
    known = {food.food_item for food in await CalorieChartRepository(db).get_by_names(units)}
    # End the read-only transaction so no DB connection is held during the Claude call.
    await db.rollback()
    return {"unknown_foods": {name: unit for name, unit in units.items() if name not in known}}


def route_after_lookup(state: VoiceUpdateState) -> str:
    return "estimate_nutrition" if state["unknown_foods"] else "save_food_logs"


async def estimate_nutrition(state: VoiceUpdateState) -> dict:
    return {"estimates": await nutrition_estimator.estimate_nutrition(state["unknown_foods"])}


async def save_food_logs(state: VoiceUpdateState, runtime: Runtime[VoiceUpdateContext]) -> dict:
    # Stages rows only; the caller owns the transaction and commits.
    db = runtime.context.db
    chart = CalorieChartRepository(db)
    await chart.add_missing(
        [
            {**food.model_dump(exclude={"metric_unit"}), "metric_unit_name": food.metric_unit}
            for food in state.get("estimates", {}).values()
        ]
    )
    items = state["food_items"]
    foods = {f.food_item: f for f in await chart.get_by_names({i.canonical_name for i in items})}
    entries = []
    for item in items:
        food = foods[item.canonical_name]
        nutrition = consumed_nutrition(food, item.metric_quantity)
        entries.append(
            EatingTrackerEntry(
                user_id=state["user_id"],
                food_item_id=food.id,
                voice_update_id=state["voice_update_id"],
                food_name_as_said=item.name,
                everyday_quantity=item.everyday_quantity,
                everyday_unit=item.everyday_unit,
                metric_quantity=item.metric_quantity,
                metric_unit=item.metric_unit,
                quantity_is_default=item.quantity_is_default,
                date_eaten=item.consumed_at.date(),
                time_eaten=item.consumed_at.time(),
                utc_offset_minutes=int(item.consumed_at.utcoffset().total_seconds() // 60),
                meal_type=item.meal.value,
                calories=nutrition.calories,
                protein_g=nutrition.protein_g,
                carbs_g=nutrition.carbs_g,
                fats_g=nutrition.fats_g,
                fibre_g=nutrition.fibre_g,
            )
        )
    await EatingTrackerRepository(db).add_all(entries)
    return {}


def build_voice_update_graph():
    graph = StateGraph(VoiceUpdateState, context_schema=VoiceUpdateContext)
    graph.add_node(classify_transcript)
    graph.add_node(extract_food_items)
    graph.add_node(save_voice_update)
    graph.add_node(lookup_foods)
    graph.add_node(estimate_nutrition)
    graph.add_node(save_food_logs)
    # All AI calls run before touching the DB, so no connection is held while waiting on them.
    graph.add_edge(START, "classify_transcript")
    graph.add_conditional_edges(
        "classify_transcript", route_after_classify, ["extract_food_items", "save_voice_update"]
    )
    graph.add_conditional_edges(
        "extract_food_items", route_after_extract, ["save_voice_update", END]
    )
    graph.add_conditional_edges("save_voice_update", route_after_save, [RESUME_NODE, END])
    graph.add_conditional_edges(
        "lookup_foods", route_after_lookup, ["estimate_nutrition", "save_food_logs"]
    )
    graph.add_edge("estimate_nutrition", "save_food_logs")
    graph.add_edge("save_food_logs", END)
    # Only our own state types may be loaded back from a checkpoint.
    serde = JsonPlusSerializer(
        allowed_msgpack_modules=[
            (t.__module__, t.__name__) for t in (FoodItem, Meal, FoodNutrition)
        ]
    )
    return graph.compile(checkpointer=InMemorySaver(serde=serde), interrupt_before=[RESUME_NODE])


# Compiled once; safe to share across concurrent requests (each run has its own thread id).
voice_update_graph = build_voice_update_graph()
