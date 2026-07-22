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
    "device_offline": ("Device offline", BinarySensorDeviceClass.CONNECTIVITY),
    "tuya_cloud_connected": ("Tuya cloud connected", BinarySensorDeviceClass.CONNECTIVITY),
}


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

    @property
    def is_on(self) -> bool:
        if self._event_type == "tuya_cloud_connected":
            status = (
                self.coordinator.data.get("settings", {})
                .get(self._device.id, {})
                .get("tuya_status", {})
            )
            return bool(status)
        events = self.coordinator.data.get("events_by_home_and_type", {}).get(
            f"{self._home.id}_{self._event_type}", []
        )
        if not events:
            return False
        latest = max(events, key=lambda event: event.time or "")
        latest_time = dt_util.parse_datetime(latest.time)
        if latest_time is None:
            return False
        if self._event_type == "device_offline":
            online = self.coordinator.data.get("events_by_home_and_type", {}).get(
                f"{self._home.id}_device_online", []
            )
            online_time = max((dt_util.parse_datetime(e.time) for e in online), default=None)
            return online_time is None or latest_time > online_time
        return latest_time >= dt_util.now() - timedelta(days=1)
