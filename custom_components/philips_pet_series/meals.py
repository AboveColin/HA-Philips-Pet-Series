"""Expanding a feeder's meal schedule into concrete occurrences.

Philips describes meals as a time plus the weekdays they repeat on, so turning
that into actual datetimes is shared by the meal calendar and the "next meal"
sensor.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging

from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

# How long a feeding is treated as "happening" — only used to give calendar
# entries a visible duration.
MEAL_DURATION = timedelta(minutes=10)


@dataclass(frozen=True)
class MealOccurrence:
    """A single scheduled feeding at a concrete moment."""

    start: datetime
    end: datetime
    name: str
    portions: object
    feed_time: str


def device_meals(coordinator, device_id) -> list:
    """Return the enabled meals belonging to one device."""
    meals = []
    for meal in coordinator.data.get("meals", []):
        if not getattr(meal, "enabled", False):
            continue
        if str(getattr(meal, "device_id", "")) != str(device_id):
            continue
        meals.append(meal)
    return meals


def _parse_feed_time(meal):
    """Return (time, is_utc) for a meal's feed time, or None if unparseable.

    A trailing "Z" means the API already reported UTC; without it the time is
    local to the account.
    """
    feed_time = getattr(meal, "feed_time", "") or ""
    try:
        if feed_time.endswith("Z"):
            return datetime.strptime(feed_time, "%H:%MZ").time(), True
        return datetime.strptime(feed_time, "%H:%M").time(), False
    except ValueError:
        _LOGGER.error(
            "Invalid feed_time for meal '%s': %r does not match HH:MM or HH:MMZ",
            getattr(meal, "name", "?"),
            feed_time,
        )
        return None


def occurrences(coordinator, device_id, start: datetime, end: datetime) -> list[MealOccurrence]:
    """Expand a device's meals into every occurrence between start and end."""
    result: list[MealOccurrence] = []
    for meal in device_meals(coordinator, device_id):
        parsed = _parse_feed_time(meal)
        if parsed is None:
            continue
        feed_time, is_utc = parsed
        # Philips numbers weekdays 1=Monday..7=Sunday; Python uses 0=Monday.
        repeat_days = {
            day - 1 for day in getattr(meal, "repeat_days", []) or [] if 1 <= day <= 7
        }
        if not repeat_days:
            continue
        current = start.date()
        # Step back a day so an occurrence that started just before the window
        # but is still running is not missed.
        current -= timedelta(days=1)
        while current <= end.date():
            if current.weekday() in repeat_days:
                naive = datetime.combine(current, feed_time)
                if is_utc:
                    begin = naive.replace(tzinfo=timezone.utc)
                else:
                    begin = dt_util.as_utc(naive)
                finish = begin + MEAL_DURATION
                if finish >= start and begin <= end:
                    result.append(
                        MealOccurrence(
                            start=begin,
                            end=finish,
                            name=getattr(meal, "name", "Meal"),
                            portions=getattr(meal, "portion_amount", None),
                            feed_time=getattr(meal, "feed_time", ""),
                        )
                    )
            current += timedelta(days=1)
    result.sort(key=lambda occurrence: occurrence.start)
    return result


def next_occurrence(coordinator, device_id, now: datetime | None = None):
    """Return the next meal that has not finished yet, if any."""
    now = now or dt_util.now()
    upcoming = occurrences(coordinator, device_id, now, now + timedelta(days=8))
    for occurrence in upcoming:
        if occurrence.end >= now:
            return occurrence
    return None
