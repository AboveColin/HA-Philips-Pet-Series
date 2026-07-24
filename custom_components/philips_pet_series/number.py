from homeassistant.components.number import NumberEntity
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
    """Set up the Philips Pets Series number entities."""
    coordinator: PhilipsPetsSeriesDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    client: PetsSeriesClient = hass.data[DOMAIN][config_entry.entry_id]["client"]

    numbers = []

    if not client.tuya_client and not getattr(client.auth, "id_token", None):
        async_add_entities(numbers)
        return

    for home, device in iter_home_devices(coordinator):
            device_id = device.id
            device_settings = coordinator.data["settings"].get(device_id, {})

            # Iterate through all datapoints
            for dp_id, dp_info in datapoints.items():
                dp_code = dp_info["dpCode"]
                dp_type = dp_info["standardType"]
                dp_path = dp_info.get("path", "tuya_status")

                if dp_type == "Integer":
                    if dp_code == "feed_abnormal":
                        # A device fault register: read-only by nature, exposed
                        # as a diagnostic sensor instead of a writable number.
                        continue
                    if dp_code == "feed_num":
                        number_entitiy = PhilipsPetsSeriesNumber(
                            coordinator, client, home, device, str(dp_id), dp_code, dp_info["properties"], dp_path
                        )
                    else:
                        number_entitiy = PhilipsPetsSeriesNumber(
                            coordinator, client, home, device, str(dp_id), dp_code, dp_info["properties"], dp_path, EntityCategory.CONFIG
                        )
                    numbers.append(number_entitiy)

    async_add_entities(numbers)

class PhilipsPetsSeriesNumber(PhilipsPetsSeriesEntity, NumberEntity):
    """Representation of a Philips Pets Series number entity for Integer datapoints."""

    def __init__(self, coordinator, client, home, device, dp_id, dp_code, properties, dp_path, category=None):
        """Initialize the number entity."""
        super().__init__(coordinator, device, home)
        self._client = client
        self._dp_id = dp_id
        self._dp_code = dp_code
        self._properties = properties
        self._dp_path = dp_path
        self._attr_unique_id = f"{device.id}_number_{dp_code}"
        # Home Assistant already prefixes the device name, so repeating it
        # here produced names like "Voederbak Video Osd (Voederbak)".
        self._attr_name = dp_code.replace('_', ' ').capitalize()
        self._attr_native_min_value = properties.get("min", 0)
        self._attr_native_max_value = properties.get("max", 100)
        self._attr_native_step = properties.get("step", 1)
        self._attr_mode = properties.get("mode", "slider")
        self._attr_native_unit_of_measurement = properties.get("unit", "")
        self._attr_native_value = self._get_current_value()
        if category:
            self._attr_entity_category = category
        _LOGGER.debug(properties)

    def _get_current_value(self):
        """Get the current value from the coordinator data."""
        settings = self._get_settings()
        if self._dp_code not in settings:
            _LOGGER.debug(
                "Datapoint %s not found in settings for device %s. Available keys: %s",
                self._dp_code,
                self._device.id,
                list(settings.keys()),
            )
        current_value = self._dp_lookup(settings)
        if current_value is self._MISSING:
            return None
        _LOGGER.debug(
            "Number Entity [%s]: current_value = %s",
            self._attr_name,
            current_value,
        )
        return current_value

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
                "Number Entity [%s] is unavailable. Device ID: %s, dp_code: %s. Available settings: %s",
                self._attr_name,
                self._device.id,
                self._dp_code,
                list(settings.keys()),
            )
        return is_available

    @property
    def native_value(self):
        """Return the current value."""
        return self._get_current_value()

    async def async_set_native_value(self, value: float) -> None:
        """Set a new value."""
        try:
            int_value = int(value)
            _LOGGER.debug(
                "Setting Number Entity [%s] to %s",
                self._attr_name,
                int_value,
            )
            dp_code = self._dp_id
            await self._client.publish_cloud_dps(
                self.coordinator.tuya_device_id(self._device),
                {dp_code: int_value},
            )
            await self.coordinator.async_request_refresh()
        except Exception as e:
            raise HomeAssistantError(
                f"Failed to set {self._attr_name} to {value}: {e}"
            ) from e
