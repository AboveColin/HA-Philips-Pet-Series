"""Tests for the event debug lines.

The lines must say which events the entities keep and which they drop, and must
never print a raw id: users paste these logs into public issues.
"""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

# Loaded straight from the file, for the same reason as in test_firmware.py.
_MODULE = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "philips_pet_series"
    / "eventlog.py"
)
_spec = importlib.util.spec_from_file_location("pps_eventlog", _MODULE)
eventlog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eventlog)

FEEDER = SimpleNamespace(id="philips-1", vendor_id="tuya-1")


def event(event_id, time, device_id=None, cluster_id=None):
    return SimpleNamespace(id=event_id, time=time, device_id=device_id, cluster_id=cluster_id)


def test_an_event_for_the_philips_id_is_kept():
    label = eventlog.owner_label(event("e1", "t", "philips-1"), [FEEDER])
    assert label == f"device {eventlog.short_id('philips-1')} (kept)"


def test_an_event_for_the_tuya_id_is_named_as_dropped():
    label = eventlog.owner_label(event("e1", "t", "tuya-1"), [FEEDER])
    assert label == f"Tuya id of device {eventlog.short_id('philips-1')} (dropped)"


def test_an_event_without_a_device_id_is_kept_and_an_empty_one_dropped():
    assert eventlog.owner_label(event("e1", "t"), [FEEDER]) == "no device id (kept)"
    assert eventlog.owner_label(event("e1", "t", ""), [FEEDER]) == "empty device id (dropped)"


def test_the_line_counts_per_device_and_names_the_newest_event():
    events = [
        event("e1", "2026-10-20T08:00:00Z", "philips-1", "c1"),
        event("e2", "2026-10-21T08:00:00Z", "philips-1", "c2"),
        event("e3", "2026-10-21T09:00:00Z", "someone-else"),
    ]
    line = eventlog.describe_events("motion_detected", events, [FEEDER])
    assert line.startswith("motion_detected: 3 events; ")
    assert (
        f"device {eventlog.short_id('philips-1')} (kept): 2, newest "
        f"{eventlog.short_id('e2')} at 2026-10-21T08:00:00Z cluster {eventlog.short_id('c2')}"
    ) in line
    assert f"unknown device {eventlog.short_id('someone-else')} (dropped): 1" in line


def test_no_events_says_so():
    assert eventlog.describe_events("food_level_low", [], [FEEDER]) == (
        "food_level_low: no events in the window"
    )


def test_no_raw_id_reaches_the_line():
    # Not hex-like ids such as "e1": a hash could contain those by chance.
    events = [
        event("event-one", "t", "philips-1", "cluster-one"),
        event("event-two", "t", "tuya-1"),
    ]
    line = eventlog.describe_events("x", events, [FEEDER])
    for raw in ("philips-1", "tuya-1", "event-one", "event-two", "cluster-one"):
        assert raw not in line
