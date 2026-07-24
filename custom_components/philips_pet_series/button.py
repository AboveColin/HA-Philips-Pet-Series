from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN, PhilipsPetsSeriesDataUpdateCoordinator
from .entity import PhilipsPetsSeriesEntity, iter_home_devices

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

    for home, device in iter_home_devices(coordinator):
            # Assuming you want one feed button per device
            if client.tuya_client or getattr(client.auth, "id_token", None):
                buttons.append(PhilipsPetsSeriesFeedButton(coordinator, client, home, device))

            # Check for filter settings to add Reset Filter button
            full_settings = coordinator.data.get("full_settings", {}).get(device.id)
            if full_settings and (
                getattr(full_settings, "filter_replacement_time", None)
                or getattr(full_settings, "filter_application_time", None)
                or (isinstance(full_settings, dict) and (
                    full_settings.get("filter_replacement_time")
                    or full_settings.get("filter_application_time")
                ))
            ):
                buttons.append(PhilipsPetsSeriesResetFilterButton(coordinator, client, home, device))

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
            # The mobile app uses DP 101 for PAW3300/feeder-essential and
            # DP 201 for the legacy feeder path. Keep this at one portion.
            dp_id = "101" if self._device.product_ctn in {"PAW3300", "PAW3320"} else "201"
            if getattr(self._client.auth, "id_token", None):
                await self._client.publish_cloud_dps(
                    self.coordinator.tuya_device_id(self._device),
                    {dp_id: 1.0},
                )
            else:
                await self.hass.async_add_executor_job(self._client.feed_num, 1)
            _LOGGER.info("Successfully triggered feed DP %s for device %s", dp_id, self._device.id)

            await self.coordinator.async_request_refresh()
        except Exception as e:
            raise HomeAssistantError(f"Failed to dispense food: {e}") from e


class PhilipsPetsSeriesResetFilterButton(PhilipsPetsSeriesEntity, ButtonEntity):
    """Representation of a Philips Pets Series reset filter button."""

    def __init__(self, coordinator, client, home, device):
        """Initialize the reset filter button."""
        super().__init__(coordinator, device, home)
        self._client = client
        self._attr_unique_id = f"{device.id}_reset_filter_button"
        self._attr_name = f"Reset Filter {device.name}"
        self._attr_icon = "mdi:filter-remove"

    async def async_press(self) -> None:
        """Handle the button press to reset the filter."""
        _LOGGER.info(f"Reset filter button pressed for device {self._device.id}")
        try:
            await self._client.devices_manager.reset_filter(self._home, self._device)
            _LOGGER.info(f"Successfully reset filter for device {self._device.id}")
            await self.coordinator.async_request_refresh()
        except Exception as e:
            raise HomeAssistantError(f"Failed to reset the filter: {e}") from e
