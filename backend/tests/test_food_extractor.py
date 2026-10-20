import asyncio

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from app.services import food_extractor
from app.services.food_extractor import ExtractionError, FoodExtraction


@pytest.fixture(autouse=True)
def _reset() -> None:
    yield
    asyncio.run(food_extractor.close_client())


def stub_claude(monkeypatch: pytest.MonkeyPatch, result: dict) -> list:
    """Replace the structured-output runnable; returns the messages it was sent."""
    seen: list = []

    def fake(messages: list) -> dict:
        seen.append(messages)
        return result

    monkeypatch.setattr(food_extractor, "_get_extractor", lambda: RunnableLambda(fake))
    return seen


def test_returns_parsed_items(monkeypatch: pytest.MonkeyPatch) -> None:
    parsed = FoodExtraction.model_validate(
        {
            "items": [
                {
                    "name": "kheer",
                    "everyday_quantity": 1,
                    "everyday_unit": "katori",
                    "metric_quantity": 150,
                    "metric_unit": "g",
                    "quantity_is_default": False,
                    "time": {"kind": "meal", "meal": "lunch", "days_ago": 0},
                    "food_recognized": True,
                    "quantity_understood": True,
                    "time_understood": True,
                }
            ]
        }
    )
    seen = stub_claude(monkeypatch, {"parsed": parsed, "raw": AIMessage(""), "parsing_error": None})
    items = asyncio.run(food_extractor.extract_food_items("1 katori kheer lunch me"))
    assert [i.name for i in items] == ["kheer"]
    system, human = seen[0]
    assert "Each food or drink is its own item" in system.content[0]["text"]
    assert "1 katori kheer lunch me" in human.content


def test_refusal_or_unparseable_output_is_extraction_error(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = AIMessage("", response_metadata={"stop_reason": "refusal"})
    stub_claude(monkeypatch, {"parsed": None, "raw": raw, "parsing_error": ValueError("bad")})
    with pytest.raises(ExtractionError, match="refusal"):
        asyncio.run(food_extractor.extract_food_items("dal"))


def test_missing_api_key_is_extraction_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(food_extractor.settings, "anthropic_api_key", None)
    with pytest.raises(ExtractionError):
        asyncio.run(food_extractor.extract_food_items("dal"))


def test_request_shape_for_sonnet_5_5(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sonnet 5.5 rejects forced tool_choice and non-default sampling; check what we'd send."""
    monkeypatch.setattr(food_extractor.settings, "anthropic_api_key", "sk-test")
    food_extractor._get_extractor()
    model = food_extractor._model
    payload = model._get_request_payload(
        [("human", "hi")],
        output_config={"format": {"type": "json_schema", "schema": {}}},
    )
    assert payload["model"] == "claude-sonnet-5-5"
    assert payload["output_config"]["effort"] == "medium"
    assert payload["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in payload["betas"]
    assert "tool_choice" not in payload
    assert "temperature" not in payload
