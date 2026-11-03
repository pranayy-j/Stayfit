"""Decide with Claude whether a new food name is a food already in the calorie chart."""

import logging
from collections.abc import Mapping

from anthropic import APIError
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from app.config import settings

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-5-5"
EFFORT = "low"
TIMEOUT_SECONDS = 60.0
MAX_TOKENS = 4_000


class FoodMatch(BaseModel):
    food: str = Field(description="The new food name exactly as given.")
    match: str | None = Field(
        description="The candidate name exactly as given that is the same food, or null if none is."
    )


class FoodMatches(BaseModel):
    matches: list[FoodMatch] = Field(description="One entry per new food given, in the same order.")


SYSTEM_PROMPT = """You keep the shared food list of a global food-tracking app free of \
duplicates. Users speak Hindi, English or Hinglish, so a food name may be in any of these, in \
Latin script ("kela", "anda", "chawal"). Foods can be from any cuisine.

You are given new food names. With each one come candidates: foods already in the list that \
look similar, each as "name | other names". For each new food, say which candidate is the same \
food, or that none is.

Same food means the same nutrition per 100 g as eaten. These are the same food:
- A translation or transliteration: kela and banana, anda and egg, chawal and rice.
- A spelling variant or synonym: chapati and roti, ladyfinger and okra.

These are different foods, even though the names are close:
- A different variety or dish: dal and dal makhani, rice and brown rice.
- A different preparation: boiled egg and fried egg, aloo and aloo fry.
- A different ripeness, part or form: kela and kacha kela, chicken breast and chicken thigh.

When unsure, answer null; a missed match only costs a new estimate, a wrong one logs the wrong \
nutrition."""


class FoodMatchingError(Exception):
    """Claude could not match foods (misconfiguration, API failure, refusal or gaps)."""


_model: ChatAnthropic | None = None
_matcher: Runnable | None = None


def _get_matcher() -> Runnable:
    global _model, _matcher
    if _matcher is None:
        if not settings.anthropic_api_key:
            raise FoodMatchingError("ANTHROPIC_API_KEY is not configured")
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
        _matcher = _model.with_structured_output(
            FoodMatches, method="json_schema", include_raw=True
        )
    return _matcher


async def close_client() -> None:
    global _model, _matcher
    if _model is not None:
        await _model._async_client.close()
    _model = _matcher = None


async def match_foods(candidates: Mapping[str, Mapping[str, str]]) -> dict[str, str]:
    """For {new food: {candidate name: its search text}}, return {new food: matching name}.

    Foods with no match are left out. Raises FoodMatchingError, also when Claude leaves out any
    food.
    """
    listing = "\n".join(
        f"<food name={food!r}>\n" + "\n".join(f"- {text}" for text in texts.values()) + "\n</food>"
        for food, texts in candidates.items()
    )
    messages = [
        SystemMessage(
            content=[
                {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
            ]
        ),
        HumanMessage(content=f"<new_foods>\n{listing}\n</new_foods>"),
    ]
    try:
        result = await _get_matcher().ainvoke(messages, config={"run_name": "food_matcher"})
    except APIError as e:
        raise FoodMatchingError(str(e)) from e

    parsed: FoodMatches | None = result["parsed"]
    if parsed is None:
        stop_reason = result["raw"].response_metadata.get("stop_reason")
        raise FoodMatchingError(f"No structured output (stop_reason={stop_reason})") from result[
            "parsing_error"
        ]

    answered = {m.food: m.match for m in parsed.matches if m.food in candidates}
    if len(answered) < len(candidates):
        # Counts only; food names are user content and stay out of logs.
        raise FoodMatchingError(f"Claude answered for {len(answered)} of {len(candidates)} foods")
    # A match must be one of that food's own candidates; anything else is ignored.
    matches = {food: m for food, m in answered.items() if m is not None and m in candidates[food]}
    logger.debug("Matched %d of %d new foods to chart foods", len(matches), len(candidates))
    return matches
