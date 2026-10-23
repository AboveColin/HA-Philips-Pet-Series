"""Decisions for a feeder that came back under a new device id.

A feeder that moves from the Philips Pet Series app to the HomeID app, or is
paired again, gets a new Philips device id. Home Assistant then keeps the old
device with unavailable entities and adds a second device next to it. The
functions here decide which device is gone, which current devices can take its
place, which entities move, and which saved meals to create again.
__init__.py and repairs.py apply the decisions to the registries.

This file imports nothing from Home Assistant, so the tests load it alone.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

# Registry devices for a home, not for a feeder, carry this prefix.
HOME_PREFIX = "home_"

_TIME = re.compile(r"^(\d{1,2}):(\d{2})")


def philips_device_id(identifiers: Iterable[tuple[str, str]], domain: str) -> str | None:
    """Return the Philips device id of a registry device, or None for a home."""
    for ident_domain, value in identifiers:
        if ident_domain == domain and not str(value).startswith(HOME_PREFIX):
            return str(value)
    return None


def candidates(model: str | None, current: Iterable[Any], registered: set[str]) -> list[Any]:
    """Return the current devices that can take the place of a gone device.

    A candidate has the same product (CTN). The devices that have no registry
    device yet come first, because a moved feeder is new to Home Assistant.
    """
    if not model:
        return []
    same = [d for d in current if getattr(d, "product_ctn", None) == model]
    return sorted(same, key=lambda d: (str(d.id) in registered, str(d.name), str(d.id)))


def default_target(replacements: list[Any], registered: set[str]) -> str | None:
    """Return the candidate to preselect, or None if the user must choose.

    Only a feeder that is new to Home Assistant is preselected. A feeder that
    it already has can be a second, working feeder of the same model, and a
    move replaces that feeder's entities.
    """
    if replacements and str(replacements[0].id) not in registered:
        return str(replacements[0].id)
    return None


def unique_id_moves(
    old_id: str, new_id: str, old_unique_ids: Iterable[str], new_unique_ids: set[str]
) -> tuple[dict[str, str], list[str]]:
    """Return (moves, drops) for the entities of the old device.

    Every entity unique_id of a device starts with "<device id>_". An old
    entity moves when the new device has the same entity: the move gives the
    old entry the new unique_id, so its entity_id, history and user settings
    stay. An old entity that the new device does not have is dropped.
    """
    prefix = f"{old_id}_"
    moves: dict[str, str] = {}
    drops: list[str] = []
    for unique_id in old_unique_ids:
        if not unique_id.startswith(prefix):
            drops.append(unique_id)
            continue
        target = f"{new_id}_{unique_id[len(prefix):]}"
        if target in new_unique_ids:
            moves[unique_id] = target
        else:
            drops.append(unique_id)
    return moves, drops


def wire_time(value: Any) -> str | None:
    """Return a meal time as "HH:MM", or None if it is not a time."""
    match = _TIME.match(str(value or ""))
    if match is None:
        return None
    return f"{int(match.group(1)):02d}:{match.group(2)}"


def meal_record(meal: Any) -> dict[str, Any] | None:
    """Return the part of a meal that is needed to create it again."""
    time = wire_time(getattr(meal, "feed_time", None))
    if time is None:
        return None
    return {
        "name": str(getattr(meal, "name", "") or ""),
        "time": time,
        "amount": getattr(meal, "portion_amount", None),
        "repeat_days": list(getattr(meal, "repeat_days", None) or []),
        "enabled": bool(getattr(meal, "enabled", True)),
    }


def schedules(devices: Iterable[Any], meals: Iterable[Any]) -> dict[str, list[dict[str, Any]]]:
    """Return the meal records of each device, sorted by time."""
    by_device: dict[str, list[dict[str, Any]]] = {str(d.id): [] for d in devices}
    for meal in meals:
        records = by_device.get(str(getattr(meal, "device_id", "")))
        record = meal_record(meal)
        if records is not None and record is not None:
            records.append(record)
    for records in by_device.values():
        records.sort(key=lambda r: (r["time"], r["name"]))
    return by_device


def merge_saved(
    saved: dict[str, dict[str, Any]],
    current: dict[str, list[dict[str, Any]]],
    names: dict[str, str],
    now: str,
) -> bool:
    """Write the current schedules into saved. Return True if saved changed.

    An empty schedule does not replace a saved one. When a feeder is removed
    from an app, its meals go first, and this keeps them for a restore.
    """
    changed = False
    for device_id, records in current.items():
        if not records:
            continue
        old = saved.get(device_id)
        if old is not None and old.get("meals") == records:
            continue
        saved[device_id] = {"name": names.get(device_id, ""), "saved_at": now, "meals": records}
        changed = True
    return changed


def meals_to_restore(
    saved: list[dict[str, Any]], current_times: set[str]
) -> list[dict[str, Any]]:
    """Return the saved meals whose time the new device does not have yet.

    The backend refuses two meals at the same time (MealTimeConflict), so a
    time that is already taken is skipped.
    """
    out = []
    for record in saved:
        if record["time"] not in current_times:
            out.append(record)
            current_times = current_times | {record["time"]}
    return out


def describe(records: Iterable[dict[str, Any]]) -> str:
    """Return one line per meal, for the repair dialog."""
    lines = []
    for record in records:
        state = "" if record.get("enabled", True) else ", off"
        name = f" {record['name']}" if record.get("name") else ""
        lines.append(f"- {record['time']}: {record['amount']}x{name}{state}")
    return "\n".join(lines)
