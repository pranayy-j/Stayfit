import asyncio
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from voyageai.error import RateLimitError

from app.db import AsyncSessionLocal, SessionLocal, async_engine
from app.models import CalorieChartItem
from app.models.calorie_chart_item import EMBEDDING_DIMENSIONS
from app.services import food_embedder
from app.services.food_embedder import EmbeddingError, search_text
from app.services.food_embedding_backfill import backfill_embeddings


class FakeVoyage:
    def __init__(self, error: Exception | None = None, drop: int = 0) -> None:
        self.calls: list[dict] = []
        self.error = error
        self.drop = drop

    async def embed(self, texts: list[str], **kwargs: object) -> SimpleNamespace:
        self.calls.append({"texts": texts, **kwargs})
        if self.error:
            raise self.error
        vectors = [[float(i)] * EMBEDDING_DIMENSIONS for i in range(len(texts))]
        return SimpleNamespace(embeddings=vectors[: len(texts) - self.drop])


@pytest.fixture
def voyage(monkeypatch: pytest.MonkeyPatch) -> FakeVoyage:
    fake = FakeVoyage()
    monkeypatch.setattr(food_embedder, "_get_client", lambda: fake)
    return fake


def test_queries_and_documents_use_their_input_type(voyage: FakeVoyage) -> None:
    asyncio.run(food_embedder.embed_queries(["kela"]))
    asyncio.run(food_embedder.embed_documents(["banana | kela"]))
    assert [(c["texts"], c["input_type"]) for c in voyage.calls] == [
        (["kela"], "query"),
        (["banana | kela"], "document"),
    ]
    assert voyage.calls[0]["model"] == food_embedder.MODEL
    assert voyage.calls[0]["output_dimension"] == EMBEDDING_DIMENSIONS


def test_no_texts_make_no_call(voyage: FakeVoyage) -> None:
    assert asyncio.run(food_embedder.embed_queries([])) == []
    assert voyage.calls == []


def test_api_error_is_an_embedding_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(food_embedder, "_get_client", lambda: FakeVoyage(RateLimitError("slow")))
    with pytest.raises(EmbeddingError, match="RateLimitError"):
        asyncio.run(food_embedder.embed_queries(["kela"]))


def test_missing_embeddings_are_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(food_embedder, "_get_client", lambda: FakeVoyage(drop=1))
    with pytest.raises(EmbeddingError, match="1 of 2"):
        asyncio.run(food_embedder.embed_queries(["kela", "anda"]))


def test_missing_key_is_an_embedding_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(food_embedder.settings, "voyage_api_key", None)
    monkeypatch.setattr(food_embedder, "_client", None)
    with pytest.raises(EmbeddingError, match="VOYAGE_API_KEY"):
        asyncio.run(food_embedder.embed_queries(["kela"]))


@pytest.mark.parametrize(
    ("aliases", "expected"),
    [
        ([], "kela"),
        (["Banana", " kele ", "banana", "kela", ""], "kela | banana, kele"),
    ],
)
def test_search_text(aliases: list[str], expected: str) -> None:
    assert search_text("kela", aliases) == expected


def test_search_text_fits_the_column() -> None:
    assert len(search_text("kela", ["x" * 600])) == food_embedder.MAX_SEARCH_TEXT_CHARS


def add_food(name: str, embedding: list[float] | None) -> uuid.UUID:
    with SessionLocal() as db:
        food = CalorieChartItem(
            food_item=name,
            everyday_unit_name="piece",
            grams_per_everyday_unit=100,
            metric_unit_name="g",
            calories_per_100=89,
            protein_g_per_100=1,
            carbs_g_per_100=23,
            fats_g_per_100=0,
            fibre_g_per_100=3,
            search_text=name if embedding else None,
            embedding=embedding,
        )
        db.add(food)
        db.commit()
        return food.id


def test_backfill_embeds_only_foods_without_one(
    voyage: FakeVoyage, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.services.food_embedding_backfill.BATCH_SIZE", 1)
    add_food("banana", [9.0] * EMBEDDING_DIMENSIONS)
    add_food("kela", None)
    add_food("anda", None)

    async def run() -> int:
        try:
            async with AsyncSessionLocal() as db:
                return await backfill_embeddings(db)
        finally:
            await async_engine.dispose()

    assert asyncio.run(run()) == 2
    # One batch per food, each embedded by its name alone as a document.
    assert sorted(c["texts"][0] for c in voyage.calls) == ["anda", "kela"]
    assert {c["input_type"] for c in voyage.calls} == {"document"}
    with SessionLocal() as db:
        foods = {f.food_item: f for f in db.scalars(select(CalorieChartItem))}
    assert foods["kela"].search_text == "kela"
    assert list(foods["kela"].embedding) == [0.0] * EMBEDDING_DIMENSIONS
    assert list(foods["banana"].embedding) == [9.0] * EMBEDDING_DIMENSIONS
