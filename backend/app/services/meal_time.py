"""Turn a spoken time reference ("1 baje", "2 hours ago", "lunch", "kal raat") into a datetime.

Pure, deterministic rules; the LLM only extracts *what was said*, never computes times.
All arithmetic happens in the recording's own UTC offset (the user's local time).
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class Meal(StrEnum):
    breakfast = "breakfast"
    brunch = "brunch"
    lunch = "lunch"
    evening_snack = "evening_snack"
    dinner = "dinner"
    late_night = "late_night"


@dataclass(frozen=True)
class MealWindow:
    start: time
    end: time  # exclusive; may be earlier than start when the window crosses midnight
    typical: time  # used when the recording falls outside the window

    def contains(self, t: time) -> bool:
        if self.start < self.end:
            return self.start <= t < self.end
        return t >= self.start or t < self.end


MEAL_WINDOWS: dict[Meal, MealWindow] = {
    Meal.breakfast: MealWindow(time(5, 0), time(10, 30), time(8, 30)),
    Meal.brunch: MealWindow(time(10, 30), time(12, 0), time(11, 15)),
    Meal.lunch: MealWindow(time(12, 0), time(15, 0), time(13, 30)),
    Meal.evening_snack: MealWindow(time(15, 0), time(19, 30), time(17, 30)),
    Meal.dinner: MealWindow(time(19, 30), time(23, 0), time(21, 0)),
    Meal.late_night: MealWindow(time(23, 0), time(5, 0), time(23, 30)),
}


class TimeReference(BaseModel):
    """What the speaker said about when they ate. Extracted by the LLM; resolved here."""

    kind: Literal["clock", "relative", "meal", "now"] = Field(
        description=(
            "clock: a clock time was said ('1 baje', 'at 9', '7:30'). "
            "relative: an offset from now ('aadha ghanta pehle', '2 hours ago'). "
            "meal: only a meal word, no clock time ('lunch', 'subah', 'raat'). "
            "now: 'now', 'abhi', 'about to', or no time said at all."
        )
    )
    clock_hour: int | None = Field(
        default=None,
        description="For kind=clock: the hour as said. 0-23 if am/pm or 24h was clear, else 1-12.",
    )
    clock_minute: int | None = Field(default=None, description="For kind=clock: minutes, or 0.")
    clock_is_ambiguous_12h: bool = Field(
        default=False,
        description="True when the hour was said without am/pm and is not a 24h value (13-23, 0).",
    )
    minutes_ago: int | None = Field(
        default=None, description="For kind=relative: how many minutes before now."
    )
    meal: Meal | None = Field(
        default=None, description="The meal word if one was said (with any kind), else null."
    )
    days_ago: int | None = Field(
        default=None,
        description=(
            "Day word: aaj/today=0, kal with past tense/yesterday=1, parso=2. "
            "null when no day word was said."
        ),
    )


def meal_at(t: time) -> Meal:
    return next(meal for meal, window in MEAL_WINDOWS.items() if window.contains(t))


def resolve_consumed_at(ref: TimeReference, recorded_at: datetime) -> datetime:
    """Apply the time rules to get when the food was eaten. `recorded_at` must be tz-aware."""
    if ref.kind == "relative" and ref.minutes_ago is not None:
        return recorded_at - timedelta(minutes=ref.minutes_ago)
    if ref.kind == "clock" and ref.clock_hour is not None:
        return _resolve_clock(ref, recorded_at)
    if ref.kind == "meal" and ref.meal is not None:
        return _resolve_meal(ref.meal, ref.days_ago, recorded_at)
    # "now", "abhi", "about to", or nothing said: recording time, shifted by any day word.
    return recorded_at - timedelta(days=ref.days_ago or 0)


def _at(day: date, t: time, recorded_at: datetime) -> datetime:
    return datetime.combine(day, t, tzinfo=recorded_at.tzinfo)


def _resolve_clock(ref: TimeReference, recorded_at: datetime) -> datetime:
    """Use the said clock time: the most recent one that isn't in the future."""
    hour, minute = ref.clock_hour % 24, ref.clock_minute or 0
    hours = {hour % 12, hour % 12 + 12} if ref.clock_is_ambiguous_12h else {hour}
    today = recorded_at.date()
    days = (
        [today - timedelta(days=ref.days_ago)]
        if ref.days_ago is not None
        else [
            today,
            today - timedelta(days=1),
        ]
    )
    candidates = [_at(day, time(h, minute), recorded_at) for day in days for h in hours]
    past = [c for c in candidates if c <= recorded_at]
    if ref.meal is not None:
        # A meal word disambiguates am/pm: "raat 9 baje" is 21:00, not 09:00.
        in_meal = [c for c in past if MEAL_WINDOWS[ref.meal].contains(c.time())]
        past = in_meal or past
    return max(past) if past else recorded_at


def _resolve_meal(meal: Meal, days_ago: int | None, recorded_at: datetime) -> datetime:
    window = MEAL_WINDOWS[meal]
    if days_ago:
        return _at(recorded_at.date() - timedelta(days=days_ago), window.typical, recorded_at)
    if window.contains(recorded_at.time()):
        return recorded_at
    # A meal whose window hasn't started yet today means the previous day's meal.
    day = recorded_at.date()
    if recorded_at.time() < window.start:
        day -= timedelta(days=1)
    return _at(day, window.typical, recorded_at)
