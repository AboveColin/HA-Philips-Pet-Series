"""Debug lines that say why an event sensor or event entity has no value.

A "Last ... Event" sensor and an event entity only see the events whose
device id matches their feeder. These lines show, per event type, how many
events the cloud returned and which device each one names, so one debug log
answers "no events" against "events for another id" for every entity at once.

Users paste these logs into public issues, so every id is hashed. The hash is
stable, which is enough to see that two lines name the same device or event.

`eventlog.py` imports nothing from Home Assistant, so the tests run under plain
pytest.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Any


def short_id(value: object) -> str:
    """A short, stable stand-in for an id that must not appear in a log."""
    if value is None:
        return "none"
    return hashlib.sha256(str(value).encode()).hexdigest()[:8]


def owner_label(event: Any, devices: Iterable[Any]) -> str:
    """Which of the home's devices this event names, in the entities' terms.

    The entities keep an event with no device id and an event whose device id
    equals the Philips device id. Every other label means the entities drop it.
    """
    device_id = getattr(event, "device_id", None)
    if device_id is None:
        return "no device id (kept)"
    if device_id == "":
        return "empty device id (dropped)"
    for device in devices:
        if str(device_id) == str(device.id):
            return f"device {short_id(device.id)} (kept)"
        vendor_id = getattr(device, "vendor_id", None)
        if vendor_id and str(device_id) == str(vendor_id):
            return f"Tuya id of device {short_id(device.id)} (dropped)"
    return f"unknown device {short_id(device_id)} (dropped)"


def describe_events(
    event_type: str, events: list[Any], devices: Iterable[Any]
) -> str:
    """One line: the event count and the newest event per named device."""
    if not events:
        return f"{event_type}: no events in the window"
    devices = list(devices)
    groups: dict[str, list[Any]] = {}
    for event in events:
        groups.setdefault(owner_label(event, devices), []).append(event)
    parts = []
    for label, group in groups.items():
        newest = max(group, key=lambda event: getattr(event, "time", "") or "")
        parts.append(
            f"{label}: {len(group)}, newest {short_id(newest.id)} "
            f"at {newest.time} cluster {short_id(getattr(newest, 'cluster_id', None))}"
        )
    return f"{event_type}: {len(events)} events; " + "; ".join(parts)
