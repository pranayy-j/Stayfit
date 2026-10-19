from datetime import datetime, time

import pytest

from app.services.meal_time import Meal, TimeReference, meal_at, resolve_consumed_at

IST = "+05:30"


def at(s: str) -> datetime:
    """'2026-10-20 20:00' in IST."""
    return datetime.fromisoformat(s.replace(" ", "T") + IST)


def resolve(recorded: str, **ref: object) -> datetime:
    return resolve_consumed_at(TimeReference(**ref), at(recorded))


@pytest.mark.parametrize(
    ("recorded", "ref", "expected"),
    [
        # The worked example: "aaj lunch me khae" at 20:00 → today 13:30.
        ("2026-10-20 20:00", {"meal": Meal.lunch, "days_ago": 0}, "2026-10-20 13:30"),
        # Recorded inside the meal's window → recording time.
        ("2026-10-20 13:10", {"meal": Meal.lunch}, "2026-10-20 13:10"),
        # Window hasn't started yet today → previous day's meal.
        ("2026-10-20 00:40", {"meal": Meal.dinner}, "2026-10-19 21:00"),
        ("2026-10-20 09:00", {"meal": Meal.lunch}, "2026-10-19 13:30"),
        # Late night crosses midnight: 02:00 is inside its window.
        ("2026-10-20 02:00", {"meal": Meal.late_night}, "2026-10-20 02:00"),
        # Day words shift the date.
        ("2026-10-20 10:00", {"meal": Meal.dinner, "days_ago": 1}, "2026-10-19 21:00"),
        ("2026-10-20 10:00", {"meal": Meal.breakfast, "days_ago": 2}, "2026-10-18 08:30"),
    ],
)
def test_meal_words(recorded: str, ref: dict, expected: str) -> None:
    assert resolve(recorded, kind="meal", **ref) == at(expected)


@pytest.mark.parametrize(
    ("recorded", "ref", "expected"),
    [
        # "1 baje" at 20:00 → most recent non-future 1 o'clock = 13:00 today.
        ("2026-10-20 20:00", {"clock_hour": 1, "clock_is_ambiguous_12h": True}, "2026-10-20 13:00"),
        # "at 9" at 08:00 → 21:00 yesterday (09:00 today is in the future).
        ("2026-10-20 08:00", {"clock_hour": 9, "clock_is_ambiguous_12h": True}, "2026-10-19 21:00"),
        # Unambiguous 24h hour.
        ("2026-10-20 20:00", {"clock_hour": 21, "clock_minute": 15}, "2026-10-19 21:15"),
        # A meal word picks am/pm: "raat 9 baje" at 23:00 → 21:00 today, not 09:00.
        (
            "2026-10-20 23:00",
            {"clock_hour": 9, "clock_is_ambiguous_12h": True, "meal": Meal.dinner},
            "2026-10-20 21:00",
        ),
        # "kal 1 baje" → yesterday, latest candidate (13:00).
        (
            "2026-10-20 08:00",
            {"clock_hour": 1, "clock_is_ambiguous_12h": True, "days_ago": 1},
            "2026-10-19 13:00",
        ),
    ],
)
def test_clock_times(recorded: str, ref: dict, expected: str) -> None:
    assert resolve(recorded, kind="clock", **ref) == at(expected)


def test_relative_time() -> None:
    assert resolve("2026-10-20 20:00", kind="relative", minutes_ago=30) == at("2026-10-20 19:30")


def test_now_or_nothing_uses_recording_time() -> None:
    assert resolve("2026-10-20 20:00", kind="now") == at("2026-10-20 20:00")
    assert resolve("2026-10-20 20:00", kind="now", days_ago=1) == at("2026-10-19 20:00")


def test_keeps_recording_offset() -> None:
    assert (
        resolve("2026-10-20 20:00", kind="meal", meal=Meal.lunch).utcoffset()
        == at("2026-10-20 00:00").utcoffset()
    )


@pytest.mark.parametrize(
    ("t", "meal"),
    [
        (time(5, 0), Meal.breakfast),
        (time(10, 30), Meal.brunch),
        (time(14, 59), Meal.lunch),
        (time(19, 29), Meal.evening_snack),
        (time(22, 0), Meal.dinner),
        (time(23, 0), Meal.late_night),
        (time(4, 59), Meal.late_night),
    ],
)
def test_meal_at(t: time, meal: Meal) -> None:
    assert meal_at(t) == meal
