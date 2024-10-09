from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

import logging

from petsseries.api import PetsSeriesClient

from . import DOMAIN, PhilipsPetsSeriesDataUpdateCoordinator
from .entity import PhilipsPetsSeriesEntity
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

    for home in coordinator.data["homes"]:
        for device in coordinator.data["devices"]:
            device_id = device.id
            device_settings = coordinator.data["settings"].get(device_id, {})
            
            # Iterate through all datapoints
            for dp_id, dp_info in datapoints.items():
                dp_code = dp_info["dpCode"]
                dp_type = dp_info["standardType"]
                dp_path = dp_info.get("path", "")

                if dp_type == "Boolean":
                    switches.append(PhilipsPetsSeriesSwitch(
                        coordinator, client, home, device, dp_code, dp_path
                    ))

    async_add_entities(switches)

class PhilipsPetsSeriesSwitch(PhilipsPetsSeriesEntity, SwitchEntity):
    """Representation of a Philips Pets Series switch."""

    def __init__(self, coordinator, client, home, device, dp_code, dp_path):
        """Initialize the switch."""
        super().__init__(coordinator, device, home)
        self._client = client
        self._dp_code = dp_code
        self._dp_path = dp_path
        self._attr_unique_id = f"{device.id}_{dp_code}"
        self._attr_name = f"{dp_code.replace('_', ' ').title()} ({device.name})"
        self._attr_icon = "mdi:toggle-switch"

    def _get_settings(self):
        """Retrieve the correct settings dictionary based on dp_path."""
        device_settings = self.coordinator.data["settings"].get(self._device.id, {})
        if self._dp_path == "tuya_status":
            return device_settings.get("tuya_status", {})
        return device_settings

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        settings = self._get_settings()
        state = settings.get(self._dp_code, False)
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
        is_available = self._dp_code in settings
        if not is_available:
            _LOGGER.warning(
                "Switch Entity [%s] is unavailable. Device ID: %s, dp_code: %s",
                self._attr_name,
                self._device.id,
                self._dp_code,
            )
        return is_available

    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        try:
            if self._dp_code == "device_active":
                await self.hass.async_add_executor_job(self._client.power_on_device, self._home, self._device.id)
            elif self._dp_code == "push_notification_motion":
                await self.hass.async_add_executor_job(self._client.enable_motion_notifications, self._home, self._device.id)
            else:
                _LOGGER.warning("Unhandled Boolean switch dp_code: %s", self._dp_code)
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error("Failed to turn on %s: %s", self._attr_name, e)

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        try:
            if self._dp_code == "device_active":
                await self.hass.async_add_executor_job(self._client.power_off_device, self._home, self._device.id)
            elif self._dp_code == "push_notification_motion":
                await self.hass.async_add_executor_job(self._client.disable_motion_notifications, self._home, self._device.id)
            else:
                _LOGGER.warning("Unhandled Boolean switch dp_code: %s", self._dp_code)
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error("Failed to turn off %s: %s", self._attr_name, e)
