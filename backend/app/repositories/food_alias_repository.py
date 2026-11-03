from collections.abc import Mapping, Sequence

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FoodAlias


class FoodAliasRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def add_missing(self, rows: Sequence[Mapping[str, object]]) -> None:
        """Insert aliases, skipping any alias another request inserted first."""
        if not rows:
            return
        await self.db.execute(
            insert(FoodAlias).on_conflict_do_nothing(index_elements=["alias"]), list(rows)
        )
