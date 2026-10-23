import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CalorieChartItem(Base):
    """One food, shared by all users. Nutrition is per 100 g (solids) or 100 ml (liquids)."""

    __tablename__ = "calorie_chart"
    __table_args__ = (
        CheckConstraint("metric_unit_name IN ('g', 'ml')", name="ck_calorie_chart_metric_unit"),
    )
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Lowercase, singular name from Claude; the lookup key.
    food_item: Mapped[str] = mapped_column(String(128), unique=True)
    everyday_unit_name: Mapped[str] = mapped_column(String(32))
    # Grams (or ml) in one everyday unit, e.g. 1 roti = 30 g.
    grams_per_everyday_unit: Mapped[float] = mapped_column(Numeric(8, 2, asdecimal=False))
    metric_unit_name: Mapped[str] = mapped_column(String(2))
    calories_per_100: Mapped[float] = mapped_column(Numeric(7, 2, asdecimal=False))
    protein_g_per_100: Mapped[float] = mapped_column(Numeric(7, 2, asdecimal=False))
    carbs_g_per_100: Mapped[float] = mapped_column(Numeric(7, 2, asdecimal=False))
    fats_g_per_100: Mapped[float] = mapped_column(Numeric(7, 2, asdecimal=False))
    fibre_g_per_100: Mapped[float] = mapped_column(Numeric(7, 2, asdecimal=False))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
