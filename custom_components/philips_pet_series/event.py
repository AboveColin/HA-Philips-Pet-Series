"""Home Assistant event entities for Philips event history."""

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN, PhilipsPetsSeriesDataUpdateCoordinator
from .entity import PhilipsPetsSeriesEntity, iter_home_devices


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PhilipsPetsSeriesDataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]["coordinator"]
    async_add_entities(
        PhilipsPetsSeriesEventEntity(coordinator, home, device, event_type)
        for home, device in iter_home_devices(coordinator)
        for event_type in coordinator.data.get("event_types", [])
        if isinstance(event_type, str) or hasattr(event_type, "value")
    )


class PhilipsPetsSeriesEventEntity(PhilipsPetsSeriesEntity, EventEntity):
    """Expose the latest occurrence with structured event attributes."""

    def __init__(self, coordinator, home, device, event_type) -> None:
        super().__init__(coordinator, device, home)
        self._event_type = getattr(event_type, "value", event_type)
        self._attr_unique_id = f"{device.id}_{self._event_type}_event"
        self._attr_name = self._event_type.replace("_", " ").title()
        self._attr_event_types = [self._event_type]

    @property
    def event(self):
        events = self.coordinator.data.get("events_by_home_and_type", {}).get(
            f"{self._home.id}_{self._event_type}", []
        )
        if not events:
            return None
        latest = max(events, key=lambda item: item.time or "")
        return latest.id

    @property
    def extra_state_attributes(self):
        events = self.coordinator.data.get("events_by_home_and_type", {}).get(
            f"{self._home.id}_{self._event_type}", []
        )
        if not events:
            return None
        latest = max(events, key=lambda item: item.time or "")
        return {"timestamp": latest.time, "source": latest.source, "url": latest.url}
