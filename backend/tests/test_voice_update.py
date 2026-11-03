import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db import SessionLocal
from app.main import app
from app.models import CalorieChartItem, EatingTrackerEntry, FoodAlias, User, VoiceUpdate
from app.models.calorie_chart_item import EMBEDDING_DIMENSIONS
from app.schemas.voice_update import MAX_TRANSCRIPT_CHARS
from app.services import (
    eating_classifier,
    food_embedder,
    food_extractor,
    food_matcher,
    nutrition_estimator,
)
from app.services.eating_classifier import ClassificationError
from app.services.food_embedder import EmbeddingError
from app.services.food_extractor import ExtractedFoodItem, ExtractionError
from app.services.food_matcher import FoodMatchingError
from app.services.meal_time import Meal, TimeReference
from app.services.nutrition_estimator import FoodNutrition, NutritionEstimationError
from app.services.token_service import create_access_token
from app.workflows.voice_update_graph import extract_food_items, voice_update_graph

client = TestClient(app)

PAYLOAD = {"voice-transcript": "Ran 5k this morning.", "timestamp": "2026-10-20T07:30:00+05:30"}


@pytest.fixture
def jev_probability(monkeypatch: pytest.MonkeyPatch) -> dict[str, float]:
    """Stub JEV; set holder["p"] to control the returned probability."""
    holder = {"p": 0.9}

    async def fake(_: str) -> float:
        return holder["p"]

    monkeypatch.setattr(eating_classifier, "eating_update_probability", fake)
    return holder


def dal(name: str = "dal", **flags: bool) -> ExtractedFoodItem:
    return ExtractedFoodItem(
        name=name,
        canonical_name=name,
        everyday_quantity=1,
        everyday_unit="katori",
        metric_quantity=150,
        metric_unit="g",
        quantity_is_default=True,
        time=TimeReference(kind="meal", meal=Meal.lunch, days_ago=0),
        **{"food_recognized": True, "quantity_understood": True, "time_understood": True, **flags},
    )


@pytest.fixture(autouse=True)
def claude_items(monkeypatch: pytest.MonkeyPatch) -> list[ExtractedFoodItem]:
    """Stub Claude; mutate the returned list to control the extracted items."""
    items = [dal()]

    async def fake(_: str) -> list[ExtractedFoodItem]:
        return items

    monkeypatch.setattr(food_extractor, "extract_food_items", fake)
    return items


def nutrition(name: str, kcal: float = 100.0, aliases: tuple[str, ...] = ()) -> FoodNutrition:
    return FoodNutrition(
        food_item=name,
        aliases=list(aliases),
        metric_unit="g",
        everyday_unit_name="katori",
        grams_per_everyday_unit=150,
        calories_per_100=kcal,
        protein_g_per_100=5,
        carbs_g_per_100=10,
        fats_g_per_100=2,
        fibre_g_per_100=1,
    )


@pytest.fixture(autouse=True)
def estimator_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    """Stub the nutrition estimate; returns the {name: unit hint} maps it was asked for."""
    calls: list[dict[str, str]] = []

    async def fake(foods: dict[str, str]) -> dict[str, FoodNutrition]:
        calls.append(dict(foods))
        return {name: nutrition(name) for name in foods}

    monkeypatch.setattr(nutrition_estimator, "estimate_nutrition", fake)
    return calls


# Fake embeddings: names in the same group get the same vector, other names unrelated ones.
SAME_FOOD = {"kela": "banana", "kele": "banana"}
_axes: dict[str, int] = {}


def fake_vector(text: str) -> list[float]:
    name = text.split(" | ", 1)[0]
    axis = _axes.setdefault(SAME_FOOD.get(name, name), len(_axes))
    return [1.0 if i == axis else 0.0 for i in range(EMBEDDING_DIMENSIONS)]


@pytest.fixture(autouse=True)
def embedder_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, list[str]]]:
    """Stub Voyage; returns the (input type, texts) of each call."""
    calls: list[tuple[str, list[str]]] = []

    def fake(input_type: str):
        async def embed(texts: list[str]) -> list[list[float]]:
            calls.append((input_type, list(texts)))
            return [fake_vector(t) for t in texts]

        return embed

    monkeypatch.setattr(food_embedder, "embed_queries", fake("query"))
    monkeypatch.setattr(food_embedder, "embed_documents", fake("document"))
    return calls


@pytest.fixture(autouse=True)
def matcher(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Stub the Claude match; set holder["matches"] to control it, read holder["calls"]."""
    holder: dict = {"matches": {}, "calls": []}

    async def fake(candidates: dict[str, dict[str, str]]) -> dict[str, str]:
        holder["calls"].append({name: dict(texts) for name, texts in candidates.items()})
        return holder["matches"]

    monkeypatch.setattr(food_matcher, "match_foods", fake)
    return holder


def add_chart_food(name: str, search_text: str | None = None, embedded: bool = True) -> uuid.UUID:
    search_text = search_text or name
    with SessionLocal() as db:
        food = CalorieChartItem(
            **nutrition(name).model_dump(exclude={"metric_unit", "aliases"}),
            metric_unit_name="g",
            search_text=search_text if embedded else None,
            embedding=fake_vector(search_text) if embedded else None,
        )
        db.add(food)
        db.commit()
        return food.id


def auth_header() -> dict[str, str]:
    with SessionLocal() as db:
        user = User(id=uuid.uuid4(), name="Jane", email="jane@example.com", timezone="Asia/Kolkata")
        db.add(user)
        db.commit()
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def test_voice_update_above_threshold_is_eating_update(jev_probability: dict) -> None:
    res = client.post("/v1/voice-update", json=PAYLOAD, headers=auth_header())
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "received"
    assert body["is_eating_update"] is True
    assert body["id"] and body["created_at"]
    assert body["eating_status"] == "accepted"
    assert "missing_details" not in body
    assert "food_items" not in body


def stored_count() -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(VoiceUpdate))


@pytest.mark.parametrize(
    ("items", "missing", "unclear"),
    [
        ([dal("hcikuje", food_recognized=False)], ["what"], ["hcikuje"]),
        ([dal(), dal("hcikuje", food_recognized=False)], ["what"], ["hcikuje"]),
        ([dal(time_understood=False)], ["when"], ["dal"]),
        ([dal(quantity_understood=False)], ["how_much"], ["dal"]),
        (
            [dal("roti", time_understood=False), dal(quantity_understood=False)],
            ["when", "how_much"],
            ["roti", "dal"],
        ),
    ],
)
def test_voice_update_unclear_item_is_422_and_stores_nothing(
    jev_probability: dict, claude_items: list, items: list, missing: list, unclear: list
) -> None:
    claude_items[:] = items
    res = client.post("/v1/voice-update", json=PAYLOAD, headers=auth_header())
    assert res.status_code == 422
    assert res.json() == {"detail": "needs_detail", "missing": missing, "items": unclear}
    assert stored_count() == 0


def test_voice_update_defaults_are_accepted(jev_probability: dict, claude_items: list) -> None:
    # "chawal aur daal lunch me": no quantity said, a default serving is fine.
    claude_items[:] = [dal("rice"), dal()]
    res = client.post("/v1/voice-update", json=PAYLOAD, headers=auth_header())
    assert res.status_code == 200
    assert res.json()["eating_status"] == "accepted"
    assert stored_count() == 1


def test_extract_node_keeps_no_items_when_one_is_unclear(claude_items: list) -> None:
    claude_items[:] = [dal("roti"), dal("hcikuje", food_recognized=False)]
    state = {"user_id": uuid.uuid4(), "transcript": "x", "client_timestamp": datetime.now(UTC)}
    update = asyncio.run(extract_food_items(state))
    assert update["eating_status"] == "needs_detail"
    assert "food_items" not in update


def test_extract_node_resolves_meal_time(claude_items: list) -> None:
    # "aaj lunch me dal khayi", recorded at 20:00 → today 13:30, lunch. Items stay server-side.
    claude_items[:] = [dal()]
    recorded_at = datetime.fromisoformat("2026-10-20T20:00:00+05:30")
    state = {
        "user_id": uuid.uuid4(),
        "transcript": "aaj lunch me dal khayi",
        "client_timestamp": recorded_at,
    }
    update = asyncio.run(extract_food_items(state))
    assert update["eating_status"] == "accepted"
    [item] = update["food_items"]
    assert item.name == "dal"
    assert item.consumed_at == datetime.fromisoformat("2026-10-20T13:30:00+05:30")
    assert item.meal == Meal.lunch


def test_voice_update_no_specific_food_needs_detail(
    jev_probability: dict, claude_items: list
) -> None:
    claude_items.clear()
    res = client.post("/v1/voice-update", json=PAYLOAD, headers=auth_header())
    assert res.status_code == 422
    assert res.json() == {"detail": "needs_detail", "missing": ["what"], "items": []}
    assert stored_count() == 0


def test_voice_update_not_eating_skips_claude(
    jev_probability: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def must_not_run(_: str) -> list:
        raise AssertionError("Claude called for a non-eating update")

    monkeypatch.setattr(food_extractor, "extract_food_items", must_not_run)
    jev_probability["p"] = 0.1
    body = client.post("/v1/voice-update", json=PAYLOAD, headers=auth_header()).json()
    assert body["eating_status"] is None


def test_voice_update_claude_failure_returns_502(
    jev_probability: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fail(_: str) -> list:
        raise ExtractionError("boom")

    monkeypatch.setattr(food_extractor, "extract_food_items", fail)
    res = client.post("/v1/voice-update", json=PAYLOAD, headers=auth_header())
    assert res.status_code == 502
    assert res.json() == {"detail": "Food extraction failed"}
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(VoiceUpdate)) == 0


def test_voice_update_is_stored(jev_probability: dict) -> None:
    jev_probability["p"] = 0.2
    before = datetime.now(UTC)
    body = client.post("/v1/voice-update", json=PAYLOAD, headers=auth_header()).json()

    with SessionLocal() as db:
        row = db.get(VoiceUpdate, uuid.UUID(body["id"]))
        user = db.scalar(select(User))
    assert row is not None
    assert row.user_id == user.id
    assert row.transcript == PAYLOAD["voice-transcript"]
    assert row.client_timestamp == datetime.fromisoformat(PAYLOAD["timestamp"])
    assert row.created_at >= before
    assert row.timezone == "Asia/Kolkata"
    assert row.is_eating_update is False


@pytest.mark.parametrize("p", [0.75, 0.2])
def test_voice_update_at_or_below_threshold_is_not(jev_probability: dict, p: float) -> None:
    jev_probability["p"] = p
    res = client.post("/v1/voice-update", json=PAYLOAD, headers=auth_header())
    assert res.json()["is_eating_update"] is False


def test_voice_update_jev_failure_returns_502(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fail(_: str) -> float:
        raise ClassificationError("boom")

    monkeypatch.setattr(eating_classifier, "eating_update_probability", fail)
    res = client.post("/v1/voice-update", json=PAYLOAD, headers=auth_header())
    assert res.status_code == 502
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(VoiceUpdate)) == 0


def test_voice_update_requires_auth() -> None:
    assert client.post("/v1/voice-update", json=PAYLOAD).status_code == 401


def test_voice_update_validates_body() -> None:
    headers = auth_header()
    missing_ts = {"voice-transcript": "hi"}
    naive_ts = {**PAYLOAD, "timestamp": "2026-10-20T07:30:00"}
    empty = {**PAYLOAD, "voice-transcript": ""}
    for body in (missing_ts, naive_ts, empty):
        assert client.post("/v1/voice-update", json=body, headers=headers).status_code == 422


def test_voice_update_too_long_transcript(jev_probability: dict) -> None:
    headers = auth_header()
    at_limit = {**PAYLOAD, "voice-transcript": "x" * MAX_TRANSCRIPT_CHARS}
    over = {**PAYLOAD, "voice-transcript": "x" * (MAX_TRANSCRIPT_CHARS + 1)}
    assert client.post("/v1/voice-update", json=at_limit, headers=headers).status_code == 200
    res = client.post("/v1/voice-update", json=over, headers=headers)
    assert res.status_code == 413
    assert res.json() == {"detail": "Transcript too long"}


# --- Background food logging -------------------------------------------------------------

EVENING = {"voice-transcript": "aaj lunch me dal khayi", "timestamp": "2026-10-20T20:00:00+05:30"}


def post_eating(payload: dict = EVENING, headers: dict[str, str] | None = None) -> dict:
    # TestClient runs background tasks before returning, so logging has finished here.
    res = client.post("/v1/voice-update", json=payload, headers=headers or auth_header())
    assert res.status_code == 200
    return res.json()


def tracker_rows() -> list[EatingTrackerEntry]:
    with SessionLocal() as db:
        return list(db.scalars(select(EatingTrackerEntry).order_by(EatingTrackerEntry.created_at)))


def chart_rows() -> dict[str, CalorieChartItem]:
    with SessionLocal() as db:
        return {f.food_item: f for f in db.scalars(select(CalorieChartItem))}


def logging_status(voice_update_id: str) -> str | None:
    with SessionLocal() as db:
        return db.get(VoiceUpdate, uuid.UUID(voice_update_id)).food_logging_status


def is_forgotten(voice_update_id: str) -> bool:
    config = {"configurable": {"thread_id": voice_update_id}}
    return asyncio.run(voice_update_graph.aget_state(config)).values == {}


def test_new_food_is_estimated_and_logged(
    jev_probability: dict, estimator_calls: list, embedder_calls: list, matcher: dict
) -> None:
    body = post_eating()

    # An empty chart has nothing similar, so Claude isn't asked to match.
    assert matcher["calls"] == []
    assert estimator_calls == [{"dal": "katori"}]
    assert embedder_calls == [("query", ["dal"]), ("document", ["dal"])]
    dal_chart = chart_rows()["dal"]
    assert dal_chart.metric_unit_name == "g"
    assert dal_chart.grams_per_everyday_unit == 150
    assert dal_chart.search_text == "dal"
    assert list(dal_chart.embedding) == fake_vector("dal")
    [row] = tracker_rows()
    with SessionLocal() as db:
        user = db.scalar(select(User))
    assert row.user_id == user.id
    assert row.voice_update_id == uuid.UUID(body["id"])
    assert row.food_item_id == dal_chart.id
    assert row.food_name_as_said == "dal"
    assert (row.everyday_quantity, row.everyday_unit) == (1, "katori")
    assert (row.metric_quantity, row.metric_unit) == (150, "g")
    assert row.quantity_is_default is True
    # "aaj lunch" said at 20:00 IST → 13:30 local, stored as is, with the +05:30 offset.
    assert row.date_eaten.isoformat() == "2026-10-20"
    assert row.time_eaten.isoformat() == "13:30:00"
    assert row.utc_offset_minutes == 330
    assert row.meal_type == "lunch"
    # 150 g at 100 kcal / 5 g protein / 10 g carbs / 2 g fat / 1 g fibre per 100 g.
    assert (row.calories, row.protein_g, row.carbs_g, row.fats_g, row.fibre_g) == (
        150,
        7.5,
        15,
        3,
        1.5,
    )
    assert logging_status(body["id"]) == "done"
    assert is_forgotten(body["id"])


def test_known_food_skips_the_estimate(jev_probability: dict, estimator_calls: list) -> None:
    with SessionLocal() as db:
        db.add(
            CalorieChartItem(
                **nutrition("dal", kcal=120).model_dump(exclude={"metric_unit", "aliases"}),
                metric_unit_name="g",
            )
        )
        db.commit()
    body = post_eating()

    assert estimator_calls == []
    [row] = tracker_rows()
    assert row.calories == 180
    assert logging_status(body["id"]) == "done"


def test_only_unknown_foods_are_estimated(
    jev_probability: dict, claude_items: list, estimator_calls: list
) -> None:
    with SessionLocal() as db:
        db.add(
            CalorieChartItem(
                **nutrition("dal").model_dump(exclude={"metric_unit", "aliases"}),
                metric_unit_name="g",
            )
        )
        db.commit()
    claude_items[:] = [dal(), dal("roti")]
    post_eating()

    assert estimator_calls == [{"roti": "katori"}]
    assert {r.food_name_as_said for r in tracker_rows()} == {"dal", "roti"}


def test_canonical_name_is_the_chart_key(
    jev_probability: dict, claude_items: list, estimator_calls: list
) -> None:
    # "do rotia, phir ek aur roti": two items, one food.
    claude_items[:] = [
        dal("rotia").model_copy(update={"canonical_name": " Roti "}),
        dal("roti"),
    ]
    post_eating()

    assert estimator_calls == [{"roti": "katori"}]
    assert list(chart_rows()) == ["roti"]
    assert [r.food_name_as_said for r in tracker_rows()] == ["rotia", "roti"]


def test_litres_are_stored_as_ml(jev_probability: dict, claude_items: list) -> None:
    claude_items[:] = [
        dal("lassi").model_copy(
            update={"everyday_unit": "glass", "metric_quantity": 0.25, "metric_unit": "l"}
        )
    ]
    post_eating()

    [row] = tracker_rows()
    assert (row.metric_quantity, row.metric_unit) == (250, "ml")


def test_meal_comes_from_the_time_when_none_is_said(
    jev_probability: dict, claude_items: list
) -> None:
    # "abhi chai pi" at 06:15 → early morning snack.
    claude_items[:] = [dal("chai").model_copy(update={"time": TimeReference(kind="now")})]
    post_eating({**EVENING, "timestamp": "2026-10-20T06:15:00+05:30"})

    [row] = tracker_rows()
    assert row.meal_type == "early_morning_snack"
    assert row.time_eaten.isoformat() == "06:15:00"


def test_estimate_failure_marks_failed_and_stores_no_food(
    jev_probability: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fail(_: dict) -> dict:
        raise NutritionEstimationError("boom")

    monkeypatch.setattr(nutrition_estimator, "estimate_nutrition", fail)
    body = post_eating()

    # The user already got their 200; the voice update stays, marked failed.
    assert body["eating_status"] == "accepted"
    assert logging_status(body["id"]) == "failed"
    assert tracker_rows() == []
    assert chart_rows() == {}
    assert is_forgotten(body["id"])


def test_not_eating_has_no_food_logging(jev_probability: dict, estimator_calls: list) -> None:
    jev_probability["p"] = 0.1
    body = client.post("/v1/voice-update", json=PAYLOAD, headers=auth_header()).json()

    assert logging_status(body["id"]) is None
    assert estimator_calls == []
    assert tracker_rows() == []
    assert is_forgotten(body["id"])


# --- Finding a food already in the chart under another name -----------------------------


def aliases() -> dict[str, uuid.UUID]:
    with SessionLocal() as db:
        return {a.alias: a.food_item_id for a in db.scalars(select(FoodAlias))}


def test_same_food_under_another_name_reuses_the_chart_food(
    jev_probability: dict,
    claude_items: list,
    estimator_calls: list,
    embedder_calls: list,
    matcher: dict,
) -> None:
    banana_id = add_chart_food("banana", "banana | kela")
    claude_items[:] = [dal("kela")]
    matcher["matches"] = {"kela": "banana"}
    body = post_eating()

    assert embedder_calls == [("query", ["kela"])]
    assert matcher["calls"] == [{"kela": {"banana": "banana | kela"}}]
    assert estimator_calls == []
    assert list(chart_rows()) == ["banana"]
    [row] = tracker_rows()
    assert row.food_item_id == banana_id
    assert row.food_name_as_said == "kela"
    assert aliases() == {"kela": banana_id}
    assert logging_status(body["id"]) == "done"


def test_saved_alias_is_found_without_embedding_or_claude(
    jev_probability: dict,
    claude_items: list,
    estimator_calls: list,
    embedder_calls: list,
    matcher: dict,
) -> None:
    banana_id = add_chart_food("banana")
    claude_items[:] = [dal("kela")]
    matcher["matches"] = {"kela": "banana"}
    headers = auth_header()
    post_eating(headers=headers)
    embedder_calls.clear()
    matcher["calls"].clear()

    post_eating(headers=headers)

    assert embedder_calls == []
    assert matcher["calls"] == []
    assert estimator_calls == []
    assert [r.food_item_id for r in tracker_rows()] == [banana_id, banana_id]


def test_similar_but_different_food_is_estimated(
    jev_probability: dict,
    claude_items: list,
    estimator_calls: list,
    embedder_calls: list,
    matcher: dict,
) -> None:
    # Claude says none of the candidates is the same food: a new chart food is added.
    add_chart_food("dal")
    claude_items[:] = [dal("dal makhani")]
    post_eating()

    assert matcher["calls"] == [{"dal makhani": {"dal": "dal"}}]
    assert estimator_calls == [{"dal makhani": "katori"}]
    assert embedder_calls[-1] == ("document", ["dal makhani"])
    assert set(chart_rows()) == {"dal", "dal makhani"}
    assert aliases() == {}


def test_only_unmatched_foods_are_estimated(
    jev_probability: dict, claude_items: list, estimator_calls: list, matcher: dict
) -> None:
    banana_id = add_chart_food("banana")
    claude_items[:] = [dal("kela"), dal("roti")]
    matcher["matches"] = {"kela": "banana"}
    post_eating()

    assert estimator_calls == [{"roti": "katori"}]
    foods = {r.food_name_as_said: r.food_item_id for r in tracker_rows()}
    assert foods["kela"] == banana_id
    assert foods["roti"] == chart_rows()["roti"].id


def test_new_food_is_embedded_with_its_other_names(
    jev_probability: dict, claude_items: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def estimate(foods: dict[str, str]) -> dict[str, FoodNutrition]:
        return {"kela": nutrition("kela", aliases=("Banana", "kele", "kela"))}

    monkeypatch.setattr(nutrition_estimator, "estimate_nutrition", estimate)
    claude_items[:] = [dal("kela")]
    post_eating()

    assert chart_rows()["kela"].search_text == "kela | banana, kele"


def test_foods_without_an_embedding_are_not_candidates(
    jev_probability: dict, claude_items: list, matcher: dict
) -> None:
    # Added before semantic search and not yet backfilled.
    add_chart_food("banana", embedded=False)
    claude_items[:] = [dal("kela")]
    post_eating()

    assert matcher["calls"] == []


def test_nearest_foods_come_first(
    jev_probability: dict, claude_items: list, matcher: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.workflows.voice_update_graph.SIMILAR_FOODS_LIMIT", 1)
    add_chart_food("roti")
    add_chart_food("banana")
    add_chart_food("dal")
    claude_items[:] = [dal("kela")]
    post_eating()

    assert matcher["calls"] == [{"kela": {"banana": "banana"}}]


@pytest.mark.parametrize("failing", ["embed", "match"])
def test_search_failure_marks_failed_and_stores_no_food(
    jev_probability: dict, claude_items: list, monkeypatch: pytest.MonkeyPatch, failing: str
) -> None:
    async def fail(_: object) -> list:
        raise EmbeddingError("boom") if failing == "embed" else FoodMatchingError("boom")

    target = (
        (food_embedder, "embed_queries") if failing == "embed" else (food_matcher, "match_foods")
    )
    monkeypatch.setattr(*target, fail)
    add_chart_food("banana")
    claude_items[:] = [dal("kela")]
    body = post_eating()

    assert logging_status(body["id"]) == "failed"
    assert tracker_rows() == []
    assert aliases() == {}
    assert list(chart_rows()) == ["banana"]
