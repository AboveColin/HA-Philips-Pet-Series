"""Home Assistant event entities for Philips event history.

Where the "Last ... Event" sensors report *when* something last happened, these
entities fire *as* it happens, which is what event triggers and automations want.

The coordinator polls history, so an occurrence is recognised by a new event id
appearing for this device rather than by a push notification.
"""

from __future__ import annotations

import logging

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN, PhilipsPetsSeriesDataUpdateCoordinator
from .entity import PhilipsPetsSeriesEntity, iter_home_devices

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PhilipsPetsSeriesDataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]["coordinator"]
    event_types = [
        getattr(event_type, "value", event_type)
        for event_type in coordinator.data.get("event_types", [])
    ]
    async_add_entities(
        PhilipsPetsSeriesEventEntity(coordinator, home, device, event_type)
        for home, device in iter_home_devices(coordinator)
        for event_type in event_types
        if isinstance(event_type, str) and event_type
    )


class PhilipsPetsSeriesEventEntity(PhilipsPetsSeriesEntity, EventEntity):
    """Fire when this device raises a given Philips event."""

    def __init__(self, coordinator, home, device, event_type) -> None:
        super().__init__(coordinator, device, home)
        self._event_type = getattr(event_type, "value", event_type)
        self._attr_unique_id = f"{device.id}_{self._event_type}_event"
        self._attr_name = self._event_type.replace("_", " ").capitalize()
        self._attr_event_types = [self._event_type]
        self._last_event_id: str | None = None

    async def async_added_to_hass(self) -> None:
        """Adopt the current history without firing for it.

        The newest known occurrence is already in the past, so treat it as seen;
        otherwise every restart would replay it as if it just happened.
        """
        await super().async_added_to_hass()
        latest = self._latest_event()
        if latest is not None:
            self._last_event_id = str(latest.id)

    def _latest_event(self):
        """This device's newest event of this type, if any.

        Events are indexed per home, so occurrences belonging to other devices
        have to be filtered out.
        """
        events = self.coordinator.data.get("events_by_home_and_type", {}).get(
            f"{self._home.id}_{self._event_type}", []
        )
        mine = [
            event
            for event in events
            if getattr(event, "device_id", None) is None
            or str(event.device_id) == str(self._device.id)
        ]
        if not mine:
            return None
        return max(mine, key=lambda event: event.time or "")

    @callback
    def _handle_coordinator_update(self) -> None:
        """Fire when a previously unseen occurrence shows up."""
        latest = self._latest_event()
        if latest is not None:
            event_id = str(latest.id)
            if event_id != self._last_event_id:
                self._last_event_id = event_id
                self._trigger_event(
                    self._event_type,
                    {
                        "event_id": event_id,
                        "timestamp": latest.time,
                        "source": getattr(latest, "source", None),
                        "url": getattr(latest, "url", None),
                    },
                )
        super()._handle_coordinator_update()
