from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN, PhilipsPetsSeriesDataUpdateCoordinator
from .entity import PhilipsPetsSeriesEntity

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Philips Pets Series button entities."""
    coordinator: PhilipsPetsSeriesDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    client = hass.data[DOMAIN][config_entry.entry_id]["client"]

    buttons = []

    for home in coordinator.data["homes"]:
        for device in coordinator.data["devices"]:
            # Assuming you want one feed button per device
            buttons.append(PhilipsPetsSeriesFeedButton(coordinator, client, home, device))

    async_add_entities(buttons)

class PhilipsPetsSeriesFeedButton(PhilipsPetsSeriesEntity, ButtonEntity):
    """Representation of a Philips Pets Series feed button."""

    def __init__(self, coordinator, client, home, device):
        """Initialize the feed button."""
        super().__init__(coordinator, device, home)
        self._client = client
        self._attr_unique_id = f"{device.id}_feed_button"
        self._attr_name = f"Feed {device.name}"
        self._attr_icon = "mdi:food"
        _LOGGER.debug(f"Initialized feed button for device {device.id}")

    async def async_press(self) -> None:
        """Handle the button press to perform a single feed action."""
        _LOGGER.info(f"Feed button pressed for device {self._device.id} ({self._device.name})")
        try:
            await self.hass.async_add_executor_job(self._client.feed_num, 1)
            _LOGGER.info(f"Successfully triggered feed_num for device {self._device.id}")
            
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error(f"Failed to execute feed_num for device {self._device.id}: {e}")
