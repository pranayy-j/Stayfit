import uuid
from collections.abc import Collection, Mapping, Sequence

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CalorieChartItem, FoodAlias


class CalorieChartRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_names(self, names: Collection[str]) -> dict[str, CalorieChartItem]:
        """Foods by chart name or alias, keyed by the name asked for. Unknown names are left out."""
        by_name = {
            food.food_item: food
            for food in await self.db.scalars(
                select(CalorieChartItem).where(CalorieChartItem.food_item.in_(names))
            )
        }
        aliased = await self.db.execute(
            select(FoodAlias.alias, CalorieChartItem)
            .join(CalorieChartItem, FoodAlias.food_item_id == CalorieChartItem.id)
            .where(FoodAlias.alias.in_(names))
        )
        for alias, food in aliased:
            by_name.setdefault(alias, food)
        return by_name

    async def nearest(self, embedding: Sequence[float], limit: int) -> list[CalorieChartItem]:
        """The foods whose embeddings are closest to `embedding` by cosine distance."""
        result = await self.db.scalars(
            select(CalorieChartItem)
            .where(CalorieChartItem.embedding.is_not(None))
            .order_by(CalorieChartItem.embedding.cosine_distance(embedding))
            .limit(limit)
        )
        return list(result)

    async def get_without_embedding(self, limit: int) -> list[CalorieChartItem]:
        result = await self.db.scalars(
            select(CalorieChartItem)
            .where(CalorieChartItem.embedding.is_(None))
            .order_by(CalorieChartItem.created_at)
            .limit(limit)
        )
        return list(result)

    async def set_embedding(
        self, food_id: uuid.UUID, search_text: str, embedding: Sequence[float]
    ) -> None:
        await self.db.execute(
            update(CalorieChartItem)
            .where(CalorieChartItem.id == food_id)
            .values(search_text=search_text, embedding=embedding)
        )

    async def add_missing(self, rows: Sequence[Mapping[str, object]]) -> None:
        """Insert foods, skipping any name another request inserted first."""
        if not rows:
            return
        await self.db.execute(
            insert(CalorieChartItem).on_conflict_do_nothing(index_elements=["food_item"]),
            list(rows),
        )
