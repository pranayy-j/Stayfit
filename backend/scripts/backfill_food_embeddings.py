"""Embed calorie-chart foods that have no embedding yet.

Run once after the semantic-search migration, from backend/:
    uv run python -m scripts.backfill_food_embeddings
"""

import asyncio
import logging

from app.db import AsyncSessionLocal, async_engine
from app.services.food_embedding_backfill import backfill_embeddings


async def main() -> None:
    async with AsyncSessionLocal() as db:
        count = await backfill_embeddings(db)
    await async_engine.dispose()
    print(f"Embedded {count} foods")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
