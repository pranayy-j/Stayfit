import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Time,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

MEAL_TYPES = (
    "early_morning_snack",
    "breakfast",
    "brunch",
    "lunch",
    "evening_snack",
    "dinner",
    "late_night_snack",
)


class EatingTrackerEntry(Base):
    """One food item a user ate, from one voice update. Nutrition is a snapshot at logging."""

    __tablename__ = "eating_tracker"
    __table_args__ = (
        Index("ix_eating_tracker_user_id_date_eaten", "user_id", "date_eaten"),
        CheckConstraint("metric_unit IN ('g', 'ml')", name="ck_eating_tracker_metric_unit"),
        CheckConstraint(
            f"meal_type IN ({', '.join(repr(m) for m in MEAL_TYPES)})",
            name="ck_eating_tracker_meal_type",
        ),
    )
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    food_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("calorie_chart.id"), index=True)
    voice_update_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("voice_updates.id", ondelete="CASCADE"), index=True
    )
    # The name exactly as the user said it, e.g. "rotia".
    food_name_as_said: Mapped[str] = mapped_column(String(128))
    # The everyday unit the user said ("bowl"), which may differ from the chart's.
    everyday_quantity: Mapped[float] = mapped_column(Numeric(10, 2, asdecimal=False))
    everyday_unit: Mapped[str] = mapped_column(String(32))
    metric_quantity: Mapped[float] = mapped_column(Numeric(10, 2, asdecimal=False))
    metric_unit: Mapped[str] = mapped_column(String(2))
    # True when no amount was said and one serving was assumed.
    quantity_is_default: Mapped[bool] = mapped_column(Boolean)
    # Local date and time where the user ate, never converted. The offset allows converting
    # on read later; timestamptz would discard it.
    date_eaten: Mapped[date] = mapped_column(Date)
    time_eaten: Mapped[time] = mapped_column(Time)
    utc_offset_minutes: Mapped[int] = mapped_column(SmallInteger)
    meal_type: Mapped[str] = mapped_column(String(32))
    calories: Mapped[float] = mapped_column(Numeric(8, 2, asdecimal=False))
    protein_g: Mapped[float] = mapped_column(Numeric(8, 2, asdecimal=False))
    carbs_g: Mapped[float] = mapped_column(Numeric(8, 2, asdecimal=False))
    fats_g: Mapped[float] = mapped_column(Numeric(8, 2, asdecimal=False))
    fibre_g: Mapped[float] = mapped_column(Numeric(8, 2, asdecimal=False))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
