import asyncio

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from app.services import food_matcher
from app.services.food_matcher import FoodMatches, FoodMatchingError


@pytest.fixture(autouse=True)
def _reset() -> None:
    yield
    asyncio.run(food_matcher.close_client())


def stub_claude(monkeypatch: pytest.MonkeyPatch, result: dict) -> list:
    """Replace the structured-output runnable; returns the messages it was sent."""
    seen: list = []

    def fake(messages: list) -> dict:
        seen.append(messages)
        return result

    monkeypatch.setattr(food_matcher, "_get_matcher", lambda: RunnableLambda(fake))
    return seen


def parsed(**matches: str | None) -> dict:
    result = FoodMatches.model_validate(
        {"matches": [{"food": food, "match": match} for food, match in matches.items()]}
    )
    return {"parsed": result, "raw": AIMessage(""), "parsing_error": None}


CANDIDATES = {
    "kela": {"banana": "banana | kele", "kacha kela": "kacha kela | raw banana"},
    "dal makhani": {"dal": "dal"},
}


def test_returns_matches_and_leaves_out_no_match(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = stub_claude(monkeypatch, parsed(kela="banana", **{"dal makhani": None}))
    assert asyncio.run(food_matcher.match_foods(CANDIDATES)) == {"kela": "banana"}
    system, human = seen[0]
    assert "same nutrition per 100 g" in system.content[0]["text"]
    assert (
        "<food name='kela'>\n- banana | kele\n- kacha kela | raw banana\n</food>" in human.content
    )
    assert "<food name='dal makhani'>\n- dal\n</food>" in human.content


def test_match_outside_the_candidates_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_claude(monkeypatch, parsed(kela="plantain", **{"dal makhani": "banana"}))
    assert asyncio.run(food_matcher.match_foods(CANDIDATES)) == {}


def test_missing_food_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_claude(monkeypatch, parsed(kela="banana"))
    with pytest.raises(FoodMatchingError, match="1 of 2 foods"):
        asyncio.run(food_matcher.match_foods(CANDIDATES))


def test_refusal_or_unparseable_output_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = AIMessage("", response_metadata={"stop_reason": "refusal"})
    stub_claude(monkeypatch, {"parsed": None, "raw": raw, "parsing_error": ValueError("bad")})
    with pytest.raises(FoodMatchingError, match="refusal"):
        asyncio.run(food_matcher.match_foods(CANDIDATES))
