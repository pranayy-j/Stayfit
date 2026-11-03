"""Estimate nutrition for foods not yet in the calorie chart, with Claude."""

import logging
from collections.abc import Mapping
from typing import Literal

from anthropic import APIError
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from app.config import settings

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-5-5"
EFFORT = "medium"
TIMEOUT_SECONDS = 60.0
MAX_TOKENS = 16_000


class FoodNutrition(BaseModel):
    """Typical nutrition of one food, per 100 g or 100 ml as eaten."""

    food_item: str = Field(description="The food name exactly as given.")
    aliases: list[str] = Field(
        description="Other common names for exactly this food, lowercase and singular: its "
        "English name if the given name is not English, and its common Hindi or Hinglish "
        'names in Latin script, e.g. "banana", "kele" for kela. Empty if there are none.'
    )
    metric_unit: Literal["g", "ml"] = Field(
        description="ml for drinks and other foods measured by volume, g for everything else."
    )
    everyday_unit_name: str = Field(
        description="The usual everyday unit: piece, katori, bowl, plate, glass, cup, spoon..."
    )
    grams_per_everyday_unit: float = Field(
        gt=0, description="Grams (or ml) of this food in one everyday unit."
    )
    calories_per_100: float = Field(ge=0, description="kcal per 100 g or 100 ml.")
    protein_g_per_100: float = Field(ge=0, description="Protein in grams per 100 g or 100 ml.")
    carbs_g_per_100: float = Field(ge=0, description="Carbohydrates in grams per 100 g or 100 ml.")
    fats_g_per_100: float = Field(ge=0, description="Fat in grams per 100 g or 100 ml.")
    fibre_g_per_100: float = Field(ge=0, description="Dietary fibre in grams per 100 g or 100 ml.")


class NutritionEstimates(BaseModel):
    foods: list[FoodNutrition] = Field(description="One entry per food given, in the same order.")


SYSTEM_PROMPT = """You estimate the nutrition of foods for a global food-tracking app. Users \
speak Hindi, English or Hinglish, so a food name may be in any of these, in Latin script \
("aloo paratha", "anda", "pasta", "chicken burger"). Foods can be from any cuisine.

For each food given, return typical values for that food as it is most commonly prepared at \
home in the cuisine it comes from: dal and sabzi as home-cooked Indian food, pasta as home-cooked \
Italian-style pasta. Follow the name when it says otherwise (restaurant, packaged, fried, a \
brand).

For each food
- food_item: the name exactly as given, unchanged.
- metric_unit: ml for drinks and other foods measured by volume (milk, chai, coffee, juice, \
soup); g for everything else, including dal, curries, rice and pasta.
- Nutrition per 100 g or per 100 ml of the food as eaten: cooked, with its usual oil, ghee, \
sugar or milk, not the raw ingredients. Calories in kcal; protein, carbs, fats and fibre in \
grams.
- everyday_unit_name: the unit people most often use for this food. A unit hint is given \
with each food; use it when it is a natural unit for that food.
- grams_per_everyday_unit: how many grams (or ml) one everyday unit of this food holds, e.g. \
1 roti is about 30 g, 1 katori of dal about 150 g, 1 glass of milk about 250 ml.

Use values in line with standard food composition tables such as IFCT and USDA. Calories \
should roughly equal 4 x protein + 4 x carbs + 9 x fats."""


class NutritionEstimationError(Exception):
    """Claude could not estimate nutrition (misconfiguration, API failure, refusal or gaps)."""


_model: ChatAnthropic | None = None
_estimator: Runnable | None = None


def _get_estimator() -> Runnable:
    global _model, _estimator
    if _estimator is None:
        if not settings.anthropic_api_key:
            raise NutritionEstimationError("ANTHROPIC_API_KEY is not configured")
        _model = ChatAnthropic(
            model=MODEL,
            api_key=settings.anthropic_api_key,
            effort=EFFORT,
            max_tokens=MAX_TOKENS,
            timeout=TIMEOUT_SECONDS,
            # Retries 429/5xx/connection errors with backoff (Anthropic SDK default is 2).
            max_retries=2,
            # On a safety decline, the API re-runs the request on a fallback model it picks.
            betas=["server-side-fallback-2026-07-01"],
            model_kwargs={"fallbacks": "default"},
        )
        # json_schema = native structured outputs; Sonnet 5.5 rejects forced tool_choice.
        _estimator = _model.with_structured_output(
            NutritionEstimates, method="json_schema", include_raw=True
        )
    return _estimator


async def close_client() -> None:
    global _model, _estimator
    if _model is not None:
        await _model._async_client.close()
    _model = _estimator = None


async def estimate_nutrition(foods: Mapping[str, str]) -> dict[str, FoodNutrition]:
    """Estimate nutrition for {food name: unit hint}, keyed by food name.

    Raises NutritionEstimationError, also when Claude leaves out any food.
    """
    listing = "\n".join(f"- {name} (unit hint: {unit})" for name, unit in foods.items())
    messages = [
        SystemMessage(
            content=[
                {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
            ]
        ),
        HumanMessage(content=f"<foods>\n{listing}\n</foods>"),
    ]
    try:
        result = await _get_estimator().ainvoke(
            messages, config={"run_name": "nutrition_estimator"}
        )
    except APIError as e:
        raise NutritionEstimationError(str(e)) from e

    estimates: NutritionEstimates | None = result["parsed"]
    if estimates is None:
        stop_reason = result["raw"].response_metadata.get("stop_reason")
        raise NutritionEstimationError(
            f"No structured output (stop_reason={stop_reason})"
        ) from result["parsing_error"]

    by_name = {food.food_item: food for food in estimates.foods if food.food_item in foods}
    if len(by_name) < len(foods):
        # Counts only; food names are user content and stay out of logs.
        raise NutritionEstimationError(
            f"Claude returned estimates for {len(by_name)} of {len(foods)} foods"
        )
    logger.debug("Estimated nutrition for %d foods", len(by_name))
    return by_name
