import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db import SessionLocal
from app.main import app
from app.models import CalorieChartItem, EatingTrackerEntry, User, VoiceUpdate
from app.schemas.voice_update import MAX_TRANSCRIPT_CHARS
from app.services import eating_classifier, food_extractor, nutrition_estimator
from app.services.eating_classifier import ClassificationError
from app.services.food_extractor import ExtractedFoodItem, ExtractionError
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


def nutrition(name: str, kcal: float = 100.0) -> FoodNutrition:
    return FoodNutrition(
        food_item=name,
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


def post_eating(payload: dict = EVENING) -> dict:
    # TestClient runs background tasks before returning, so logging has finished here.
    res = client.post("/v1/voice-update", json=payload, headers=auth_header())
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


def test_new_food_is_estimated_and_logged(jev_probability: dict, estimator_calls: list) -> None:
    body = post_eating()

    assert estimator_calls == [{"dal": "katori"}]
    dal_chart = chart_rows()["dal"]
    assert dal_chart.metric_unit_name == "g"
    assert dal_chart.grams_per_everyday_unit == 150
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
                **nutrition("dal", kcal=120).model_dump(exclude={"metric_unit"}),
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
                **nutrition("dal").model_dump(exclude={"metric_unit"}), metric_unit_name="g"
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
