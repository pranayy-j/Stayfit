from collections.abc import Collection, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CalorieChartItem


class CalorieChartRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_names(self, names: Collection[str]) -> list[CalorieChartItem]:
        result = await self.db.scalars(
            select(CalorieChartItem).where(CalorieChartItem.food_item.in_(names))
        )
        return list(result)

    async def add_missing(self, rows: Sequence[Mapping[str, object]]) -> None:
        """Insert foods, skipping any name another request inserted first."""
        if not rows:
            return
        await self.db.execute(
            insert(CalorieChartItem).on_conflict_do_nothing(index_elements=["food_item"]),
            list(rows),
        )
