import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class FoodAlias(Base):
    """Another name for a calorie-chart food, e.g. "kela" for banana. Shared by all users.

    Added when Claude confirms a new name is the same food as one already in the chart, so the
    next time that name is said it is found by exact match, with no embedding or Claude call.
    """

    __tablename__ = "food_aliases"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Lowercase, singular, like CalorieChartItem.food_item; never equal to a chart name.
    alias: Mapped[str] = mapped_column(String(128), unique=True)
    food_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("calorie_chart.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
