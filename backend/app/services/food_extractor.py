"""Extract food items, quantities and time references from a transcript with Claude."""

import logging
from typing import Literal

from anthropic import APIError
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from app.config import settings
from app.services.meal_time import TimeReference

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-5-5"
EFFORT = "medium"
TIMEOUT_SECONDS = 60.0
MAX_TOKENS = 16_000


class ExtractedFoodItem(BaseModel):
    """One food or drink the speaker consumed (or will consume)."""

    name: str = Field(description="Food or drink name, keeping any named variety.")
    everyday_quantity: float = Field(description="Amount in an everyday unit, e.g. 2 for 2 roti.")
    everyday_unit: str = Field(
        description="Everyday unit: piece, katori, bowl, plate, glass, cup, spoon, scoop, slice..."
    )
    metric_quantity: float = Field(description="The same amount in grams or litres.")
    metric_unit: Literal["g", "l"] = Field(description="g for solids, l for liquids.")
    quantity_is_default: bool = Field(
        description="True when no quantity was said and one natural serving was assumed."
    )
    time: TimeReference


class FoodExtraction(BaseModel):
    items: list[ExtractedFoodItem] = Field(
        description="Every specific food or drink item. Empty if no specific food is named."
    )


SYSTEM_PROMPT = """You extract what a person ate or drank from a short voice note transcript. \
Transcripts are often Hinglish (Hindi and English mixed, in Latin script). Only extract the \
speaker's own eating, past, present or future. Ignore food eaten by relatives, friends, family \
or anyone else mentioned.

For each item answer three questions: what the food item is, how much was consumed, and when it \
was consumed.

Items
- Each food or drink is its own item. "kheer ke sath do rotia aur dal" gives kheer, roti and dal.
- A named variety is kept. "dal makhani" stays dal makhani, and plain "dal" stays dal.
- If the speaker corrects themselves, the last version wins. "2 roti... nahi, 3 roti" gives 3.
- If no specific food is named (only a vague category like "kuch khaya", "snacks khaye"), \
return no items.

Quantity
- Quantity can be said in metric units or in everyday units like bowl, spoon, glass, scoop, \
katori, piece, plate. Always return both: the everyday amount and unit, and the same amount in \
grams (solids) or litres (liquids).
- Convert using the food itself: 1 scoop of whey protein weighs differently than 1 scoop of ice \
cream; 1 katori of dal differs from 1 katori of rice.
- Pounds and ounces are converted to grams; fluid ounces to litres.
- If the amount is given in metric, still give the closest everyday unit (e.g. 200 g cooked rice \
is about 1 katori).
- If no quantity is said, assume 1 natural serving of that food and set quantity_is_default. \
"had egg" is 1 piece of egg with its weight in grams. "subah dal khai thi" is 1 katori of dal \
with the weight of one katori of dal.

Time
Do not compute dates or times. Report only what was said, per item, in the time fields:
- A clock time was said ("1 baje", "at 9"): kind=clock with the hour and minute as said.
- A relative time was said ("aadha ghanta pehele", "2 hours ago"): kind=relative with minutes.
- Only a meal word was said: kind=meal. Meal words: breakfast, subah, subah ka nashta -> \
breakfast; brunch -> brunch; lunch, din, din ka khana, dopahar -> lunch; hi-tea, snacks, shaam, \
shaam ki chai -> evening_snack; dinner, raat, raat ka khana -> dinner; late night, midnight \
snack -> late_night. Also set meal when a meal word comes with a clock time.
- "now", "abhi", "about to", or nothing said: kind=now.
- Day words: aaj is days_ago=0, kal with past tense is 1, parso is 2; otherwise null.
- A time said once applies to every item it covers.

Example: "1 katori kheer ke sath do rotia aur dal aaj lunch me khae" gives kheer 1 katori, \
roti 2 piece, dal 1 katori (quantity_is_default), each with kind=meal, meal=lunch, days_ago=0."""


class ExtractionError(Exception):
    """Claude could not extract food items (misconfiguration, API failure or refusal)."""


_model: ChatAnthropic | None = None
_extractor: Runnable | None = None


def _get_extractor() -> Runnable:
    global _model, _extractor
    if _extractor is None:
        if not settings.anthropic_api_key:
            raise ExtractionError("ANTHROPIC_API_KEY is not configured")
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
        _extractor = _model.with_structured_output(
            FoodExtraction, method="json_schema", include_raw=True
        )
    return _extractor


async def close_client() -> None:
    global _model, _extractor
    if _model is not None:
        await _model._async_client.close()
    _model = _extractor = None


async def extract_food_items(transcript: str) -> list[ExtractedFoodItem]:
    """Ask Claude for the food items in the transcript. Raises ExtractionError."""
    messages = [
        SystemMessage(
            content=[
                {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
            ]
        ),
        HumanMessage(content=f"<transcript>\n{transcript}\n</transcript>"),
    ]
    try:
        result = await _get_extractor().ainvoke(messages, config={"run_name": "food_extractor"})
    except APIError as e:
        raise ExtractionError(str(e)) from e

    extraction: FoodExtraction | None = result["parsed"]
    if extraction is None:
        stop_reason = result["raw"].response_metadata.get("stop_reason")
        raise ExtractionError(f"No structured output (stop_reason={stop_reason})") from result[
            "parsing_error"
        ]
    logger.debug("Extracted %d food items", len(extraction.items))
    return extraction.items
