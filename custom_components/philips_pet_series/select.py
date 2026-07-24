from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory

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
    """Set up the Philips Pets Series select entities."""
    coordinator: PhilipsPetsSeriesDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    client: PetsSeriesClient = hass.data[DOMAIN][config_entry.entry_id]["client"]
    _attr_entity_registry_enabled_default = True  # Add this line

    selects = []

    if not client.tuya_client and not getattr(client.auth, "id_token", None):
        async_add_entities(selects)
        return

    for home, device in iter_home_devices(coordinator):
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
                        coordinator, client, home, device, str(dp_id), dp_code, options, nicenames, dp_path
                    ))

    async_add_entities(selects)


class PhilipsPetsSeriesSelect(PhilipsPetsSeriesEntity, SelectEntity):
    """Representation of a Philips Pets Series select entity for Enum datapoints."""

    def __init__(self, coordinator, client, home, device, dp_id, dp_code, options, nicenames, dp_path):
        """Initialize the select entity."""
        super().__init__(coordinator, device, home)
        self._client = client
        self._dp_id = dp_id
        self._dp_code = dp_code
        self._options = options
        self._nicenames = nicenames
        self._dp_path = dp_path
        self._attr_unique_id = f"{device.id}_select_{dp_code}"
        self._attr_name = f"{dp_code.replace('_', ' ').title()} ({device.name})"
        self._value_to_nicename = {str(k): v for k, v in zip(options, nicenames)}
        self._nicename_to_value = {v: str(k) for k, v in zip(options, nicenames)}
        self._attr_options = nicenames
        self._attr_current_option = self._get_current_option()
        self._attr_entity_category = EntityCategory.CONFIG

    def _get_current_option(self):
        """Get the current option from the coordinator data."""
        settings = self._get_settings()
        current_value = self._dp_lookup(settings)
        if current_value is self._MISSING:
            return None
        current_value_str = str(current_value)
        # An unmapped value is genuinely unknown; reporting the first option
        # would silently misreport the device's real setting.
        current_option = self._value_to_nicename.get(current_value_str)
        _LOGGER.debug(
            "Select Entity [%s]: current_option = %s (value: %s)",
            self._attr_name,
            current_option,
            current_value,
        )
        return current_option

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
        is_available = self._dp_lookup(settings) is not self._MISSING
        if not is_available:
            _LOGGER.debug(
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
            await self._client.publish_cloud_dps(
                self.coordinator.tuya_device_id(self._device),
                {self._dp_id: value},
            )
            await self.coordinator.async_request_refresh()
        except Exception as e:
            raise HomeAssistantError(
                f"Failed to set {self._attr_name} to {option}: {e}"
            ) from e
