"""Binary state derived from the latest Philips event history."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import DOMAIN, PhilipsPetsSeriesDataUpdateCoordinator
from .entity import PhilipsPetsSeriesEntity, iter_home_devices

_CONDITIONS = {
    "food_level_low": ("Food level low", BinarySensorDeviceClass.PROBLEM),
    "food_outlet_stuck": ("Food outlet stuck", BinarySensorDeviceClass.PROBLEM),
    "filter_replacement_due": ("Filter replacement due", BinarySensorDeviceClass.PROBLEM),
    # Named for what "on" means: connectivity renders on="Connected".  The
    # legacy key stays "device_offline" so unique_ids (and therefore existing
    # entity IDs and history) are preserved.
    "device_offline": ("Device connectivity", BinarySensorDeviceClass.CONNECTIVITY),
    "tuya_cloud_connected": ("Tuya cloud connected", BinarySensorDeviceClass.CONNECTIVITY),
}

# Conditions reported by Philips as one-shot notifications with no matching
# "resolved" event.  The device's live Tuya fault datapoint is authoritative for
# clearing them; the event history only ever says a fault *happened*.
_FAULT_CONDITIONS = ("food_level_low", "food_outlet_stuck", "filter_replacement_due")

# Tuya DP 255 ("feed_abnormal") is a fault bitmask.  Zero unambiguously means
# "device reports no fault"; the meaning of individual bits is not known, so a
# non-zero value only prevents an automatic clear, it never raises a condition
# on its own.
_FEED_ABNORMAL_DP = "255"
_FEED_ABNORMAL_CODE = "feed_abnormal"

# How long a fault notification is trusted when no live datapoint and no
# subsequent activity can confirm the device recovered.  Only a fallback: with
# Tuya datapoints available the sensor clears as soon as the device says so.
_FAULT_FALLBACK_WINDOW = timedelta(days=1)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PhilipsPetsSeriesDataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]["coordinator"]
    async_add_entities(
        PhilipsPetsSeriesConditionSensor(coordinator, home, device, event_type)
        for home, device in iter_home_devices(coordinator)
        for event_type in _CONDITIONS
    )


class PhilipsPetsSeriesConditionSensor(PhilipsPetsSeriesEntity, BinarySensorEntity):
    """Expose alarm/connectivity conditions separately from last-event sensors."""

    def __init__(self, coordinator, home, device, event_type: str) -> None:
        super().__init__(coordinator, device, home)
        self._event_type = event_type
        self._attr_unique_id = f"{device.id}_{event_type}"
        self._attr_name = _CONDITIONS[event_type][0]
        self._attr_device_class = _CONDITIONS[event_type][1]

    def _tuya_status(self) -> dict:
        """Return the device's live Tuya datapoint snapshot (may be empty)."""
        return (
            self.coordinator.data.get("settings", {})
            .get(self._device.id, {})
            .get("tuya_status", {})
        ) or {}

    def _latest_event_time(self, event_type: str):
        """Latest timestamp for ``event_type`` *on this device*.

        The coordinator indexes events per home, but this entity represents a
        single device, so events belonging to other devices in the same home
        must be filtered out.  Events that do not carry a device id are treated
        as belonging to the device (single-device homes report them that way).
        """
        events = self.coordinator.data.get("events_by_home_and_type", {}).get(
            f"{self._home.id}_{event_type}", []
        )
        times = []
        for event in events:
            device_id = getattr(event, "device_id", None)
            if device_id is not None and str(device_id) != str(self._device.id):
                continue
            parsed = dt_util.parse_datetime(event.time or "")
            if parsed is not None:
                times.append(parsed)
        return max(times, default=None)

    def _feed_abnormal(self) -> int | None:
        """Live Tuya fault bitmask, or None when the datapoint is unavailable."""
        status = self._tuya_status()
        for key in (_FEED_ABNORMAL_DP, _FEED_ABNORMAL_CODE):
            if key in status:
                try:
                    return int(status[key])
                except (TypeError, ValueError):
                    return None
        return None

    @property
    def is_on(self) -> bool | None:
        if self._event_type == "tuya_cloud_connected":
            return bool(self._tuya_status())

        if self._event_type == "device_offline":
            # Connectivity semantics: on == connected.
            offline_time = self._latest_event_time("device_offline")
            online_time = self._latest_event_time("device_online")
            if offline_time is None and online_time is None:
                # No connectivity history at all: fall back to whether the
                # device is talking to the Tuya cloud, and report unknown if
                # even that is unavailable.  Never claim "disconnected" purely
                # because no events have been recorded yet.
                status = self._tuya_status()
                return bool(status) if status else None
            if offline_time is None:
                return True
            if online_time is None:
                return False
            return online_time >= offline_time

        latest_time = self._latest_event_time(self._event_type)
        if latest_time is None:
            return False

        if self._event_type in _FAULT_CONDITIONS:
            # The device's own fault register is authoritative: zero means the
            # condition is resolved (e.g. the hopper was refilled), so clear
            # immediately instead of waiting out a timer.
            feed_abnormal = self._feed_abnormal()
            if feed_abnormal == 0:
                return False
            if feed_abnormal is None:
                # No Tuya datapoints (cloud-only setup).  A meal dispensed
                # after the warning implies food reached the bowl, which is the
                # closest thing to a "resolved" signal the event API offers.
                dispensed = self._latest_event_time("meal_dispensed")
                if (
                    self._event_type == "food_level_low"
                    and dispensed is not None
                    and dispensed > latest_time
                ):
                    return False
            return latest_time >= dt_util.now() - _FAULT_FALLBACK_WINDOW

        return latest_time >= dt_util.now() - _FAULT_FALLBACK_WINDOW
