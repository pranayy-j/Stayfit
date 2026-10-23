from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EatingTrackerEntry


class EatingTrackerRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def add_all(self, entries: Sequence[EatingTrackerEntry]) -> None:
        """Stage the entries and flush so DB constraints apply now."""
        self.db.add_all(entries)
        await self.db.flush()
