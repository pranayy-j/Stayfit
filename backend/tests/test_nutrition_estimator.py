import asyncio

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from app.services import nutrition_estimator
from app.services.nutrition_estimator import NutritionEstimates, NutritionEstimationError


@pytest.fixture(autouse=True)
def _reset() -> None:
    yield
    asyncio.run(nutrition_estimator.close_client())


def stub_claude(monkeypatch: pytest.MonkeyPatch, result: dict) -> list:
    """Replace the structured-output runnable; returns the messages it was sent."""
    seen: list = []

    def fake(messages: list) -> dict:
        seen.append(messages)
        return result

    monkeypatch.setattr(nutrition_estimator, "_get_estimator", lambda: RunnableLambda(fake))
    return seen


def estimate(name: str) -> dict:
    return {
        "food_item": name,
        "aliases": [],
        "metric_unit": "g",
        "everyday_unit_name": "piece",
        "grams_per_everyday_unit": 30,
        "calories_per_100": 297,
        "protein_g_per_100": 9.8,
        "carbs_g_per_100": 46,
        "fats_g_per_100": 7.5,
        "fibre_g_per_100": 9,
    }


def parsed(*names: str) -> dict:
    estimates = NutritionEstimates.model_validate({"foods": [estimate(n) for n in names]})
    return {"parsed": estimates, "raw": AIMessage(""), "parsing_error": None}


def test_returns_estimates_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = stub_claude(monkeypatch, parsed("roti", "dal"))
    result = asyncio.run(nutrition_estimator.estimate_nutrition({"roti": "piece", "dal": "bowl"}))
    assert set(result) == {"roti", "dal"}
    assert result["roti"].calories_per_100 == 297
    system, human = seen[0]
    assert "per 100 g or per 100 ml" in system.content[0]["text"]
    assert "- roti (unit hint: piece)" in human.content
    assert "- dal (unit hint: bowl)" in human.content


def test_extra_foods_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_claude(monkeypatch, parsed("roti", "ghee"))
    result = asyncio.run(nutrition_estimator.estimate_nutrition({"roti": "piece"}))
    assert set(result) == {"roti"}


def test_missing_food_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_claude(monkeypatch, parsed("roti"))
    with pytest.raises(NutritionEstimationError, match="1 of 2 foods"):
        asyncio.run(nutrition_estimator.estimate_nutrition({"roti": "piece", "dal": "katori"}))


def test_refusal_or_unparseable_output_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = AIMessage("", response_metadata={"stop_reason": "refusal"})
    stub_claude(monkeypatch, {"parsed": None, "raw": raw, "parsing_error": ValueError("bad")})
    with pytest.raises(NutritionEstimationError, match="refusal"):
        asyncio.run(nutrition_estimator.estimate_nutrition({"roti": "piece"}))


def test_negative_values_are_rejected() -> None:
    with pytest.raises(ValueError):
        NutritionEstimates.model_validate({"foods": [{**estimate("roti"), "calories_per_100": -1}]})
