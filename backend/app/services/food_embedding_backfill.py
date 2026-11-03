"""Embed calorie-chart foods added before semantic search, so they can be found by meaning."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.calorie_chart_repository import CalorieChartRepository
from app.services import food_embedder

logger = logging.getLogger(__name__)

BATCH_SIZE = 100


async def backfill_embeddings(db: AsyncSession) -> int:
    """Embed every food with no embedding, a batch per commit. Returns how many were embedded.

    Their other names are unknown, so each is embedded by its name alone.
    """
    chart = CalorieChartRepository(db)
    done = 0
    while foods := await chart.get_without_embedding(BATCH_SIZE):
        # Read before the rollback, which expires the loaded rows.
        ids = [food.id for food in foods]
        texts = [food_embedder.search_text(food.food_item, []) for food in foods]
        # Don't hold the DB connection while waiting on Voyage.
        await db.rollback()
        vectors = await food_embedder.embed_documents(texts)
        for food_id, text, vector in zip(ids, texts, vectors, strict=True):
            await chart.set_embedding(food_id, text, vector)
        await db.commit()
        done += len(foods)
        logger.info("Embedded %d chart foods so far", done)
    return done
