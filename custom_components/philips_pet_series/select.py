from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory

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
    """Set up the Philips Pets Series select entities."""
    coordinator: PhilipsPetsSeriesDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    client: PetsSeriesClient = hass.data[DOMAIN][config_entry.entry_id]["client"]
    _attr_entity_registry_enabled_default = True  # Add this line

    selects = []

    for home in coordinator.data["homes"]:
        for device in coordinator.data["devices"]:
            device_id = device.id
            device_settings = coordinator.data["settings"].get(device_id, {})
            
            # Iterate through all datapoints
            for dp_id, dp_info in datapoints.items():
                dp_code = dp_info["dpCode"]
                dp_type = dp_info["standardType"]
                dp_path = dp_info.get("path", "tuya_status")

                if dp_type == "Enum":
                    options = dp_info["valueRange"]
                    nicenames = dp_info.get("niceNames", options)
                    selects.append(PhilipsPetsSeriesSelect(
                        coordinator, client, home, device, dp_code, options, nicenames, dp_path
                    ))

    async_add_entities(selects)


class PhilipsPetsSeriesSelect(PhilipsPetsSeriesEntity, SelectEntity):
    """Representation of a Philips Pets Series select entity for Enum datapoints."""

    def __init__(self, coordinator, client, home, device, dp_code, options, nicenames, dp_path):
        """Initialize the select entity."""
        super().__init__(coordinator, device, home)
        self._client = client
        self._dp_code = dp_code
        self._options = options
        self._nicenames = nicenames
        self._dp_path = dp_path
        self._attr_unique_id = f"{device.id}_{dp_code}"
        self._attr_name = f"{dp_code.replace('_', ' ').title()} ({device.name})"
        self._value_to_nicename = {str(k): v for k, v in zip(options, nicenames)}
        self._nicename_to_value = {v: str(k) for k, v in zip(options, nicenames)}
        self._attr_options = nicenames
        self._attr_current_option = self._get_current_option()
        self._attr_entity_category = EntityCategory.CONFIG

    def _get_current_option(self):
        """Get the current option from the coordinator data."""
        settings = self._get_settings()
        current_value = settings.get(self._dp_code, self._options[0])
        current_value_str = str(current_value)
        current_option = self._value_to_nicename.get(current_value_str, self._nicenames[0])
        _LOGGER.debug(
            "Select Entity [%s]: current_option = %s (value: %s)",
            self._attr_name,
            current_option,
            current_value,
        )
        return current_option

    def _get_settings(self):
        """Retrieve the correct settings dictionary based on dp_path."""
        device_settings = self.coordinator.data["settings"].get(self._device.id, {})
        if self._dp_path == "tuya_status":
            tuya_status = device_settings.get("tuya_status", {})
            if isinstance(tuya_status, list):
                # Convert list of {'code': ..., 'value': ...} dicts to a mapping
                status_dict = {item['code']: item['value'] for item in tuya_status}
                return status_dict
            elif isinstance(tuya_status, dict):
                return tuya_status
            else:
                return {}
        return device_settings

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        parent_available = super().available
        if not parent_available:
            return False
        settings = self._get_settings()
        is_available = self._dp_code in settings
        if not is_available:
            _LOGGER.warning(
                "Select Entity [%s] is unavailable. Device ID: %s, dp_code: %s. Available settings: %s",
                self._attr_name,
                self._device.id,
                self._dp_code,
                list(settings.keys()),
            )
        return is_available

    @property
    def current_option(self):
        """Return the current selected option."""
        return self._get_current_option()

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        value = self._nicename_to_value.get(option)
        if value is None:
            _LOGGER.error("Invalid option selected: %s", option)
            return
        try:
            _LOGGER.debug(
                "Setting Select Entity [%s] to %s (value: %s)",
                self._attr_name,
                option,
                value,
            )
            await self.hass.async_add_executor_job(self._client.set_tuya_value, self._dp_code, value)
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error("Failed to set %s to %s: %s", self._attr_name, option, e)
