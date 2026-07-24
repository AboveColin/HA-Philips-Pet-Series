from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

import logging

from petsseries.api import PetsSeriesClient

from . import DOMAIN, PhilipsPetsSeriesDataUpdateCoordinator
from .entity import PhilipsPetsSeriesEntity, iter_home_devices
from .datapoints import datapoints

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Philips Pets Series switches."""
    coordinator: PhilipsPetsSeriesDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    client: PetsSeriesClient = hass.data[DOMAIN][config_entry.entry_id]["client"]
    _attr_entity_registry_enabled_default = True  # Add this line

    switches = []

    if not client.tuya_client and not getattr(client.auth, "id_token", None):
        async_add_entities(switches)
        return

    for home, device in iter_home_devices(coordinator):
            device_id = device.id
            device_settings = coordinator.data["settings"].get(device_id, {})

            # Iterate through all datapoints
            for dp_id, dp_info in datapoints.items():
                dp_code = dp_info["dpCode"]
                dp_type = dp_info["standardType"]
                dp_path = dp_info.get("path", "")

                if dp_type == "Boolean":
                    switches.append(PhilipsPetsSeriesSwitch(
                        coordinator, client, home, device, str(dp_id), dp_code, dp_path
                    ))

    async_add_entities(switches)

class PhilipsPetsSeriesSwitch(PhilipsPetsSeriesEntity, SwitchEntity):
    """Representation of a Philips Pets Series switch."""

    def __init__(self, coordinator, client, home, device, dp_id, dp_code, dp_path):
        """Initialize the switch."""
        super().__init__(coordinator, device, home)
        self._client = client
        self._dp_id = dp_id
        self._dp_code = dp_code
        self._dp_path = dp_path
        self._attr_unique_id = f"{device.id}_switch_{dp_code}"
        # Home Assistant already prefixes the device name, so repeating it
        # here produced names like "Voederbak Video Osd (Voederbak)".
        self._attr_name = dp_code.replace('_', ' ').capitalize()
        self._attr_icon = "mdi:toggle-switch"

    _MISSING = object()

    def _dp_lookup(self, settings):
        """Return the datapoint value, or ``_MISSING`` when absent.

        The cloud status is keyed by numeric datapoint id and only gains the
        readable dpCode aliases when the alias pass runs, so a lookup by code
        alone reports the entity unavailable whenever the fallback status dict
        is in use.  Accept either key.
        """
        for key in (self._dp_code, self._dp_id, str(self._dp_id)):
            if key in settings:
                return settings[key]
        return self._MISSING

    def _get_settings(self):
        """Retrieve the correct settings dictionary based on dp_path."""
        device_settings = self.coordinator.data["settings"].get(self._device.id, {})
        if self._dp_path == "tuya_status":
            return device_settings.get("tuya_status", {})
        return device_settings

    @property
    def is_on(self) -> bool | None:
        """Return true if the switch is on, or None when unknown."""
        settings = self._get_settings()
        state = self._dp_lookup(settings)
        if state is self._MISSING:
            return None
        _LOGGER.debug(
            "Switch Entity [%s]: is_on = %s",
            self._attr_name,
            state,
        )
        return state

    @property
    def available(self):
        """Return True if entity is available."""
        settings = self._get_settings()
        is_available = self._dp_lookup(settings) is not self._MISSING
        if not is_available:
            _LOGGER.debug(
                "Switch Entity [%s] is unavailable. Device ID: %s, dp_code: %s",
                self._attr_name,
                self._device.id,
                self._dp_code,
            )
        return is_available

    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        try:
            await self._client.publish_cloud_dps(
                self.coordinator.tuya_device_id(self._device),
                {self._dp_id: True},
            )
            await self.coordinator.async_request_refresh()
        except Exception as e:
            raise HomeAssistantError(f"Failed to turn on {self._attr_name}: {e}") from e

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        try:
            await self._client.publish_cloud_dps(
                self.coordinator.tuya_device_id(self._device),
                {self._dp_id: False},
            )
            await self.coordinator.async_request_refresh()
        except Exception as e:
            raise HomeAssistantError(f"Failed to turn off {self._attr_name}: {e}") from e
