from re import L
from homeassistant.components.number import NumberEntity
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
    """Set up the Philips Pets Series number entities."""
    coordinator: PhilipsPetsSeriesDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    client: PetsSeriesClient = hass.data[DOMAIN][config_entry.entry_id]["client"]

    numbers = []

    for home in coordinator.data["homes"]:
        for device in coordinator.data["devices"]:
            device_id = device.id
            device_settings = coordinator.data["settings"].get(device_id, {})
            
            # Iterate through all datapoints
            for dp_id, dp_info in datapoints.items():
                dp_code = dp_info["dpCode"]
                dp_type = dp_info["standardType"]
                dp_path = dp_info.get("path", "tuya_status")

                if dp_type == "Integer":
                    if dp_code == "feed_num":
                        number_entitiy = PhilipsPetsSeriesNumber(
                            coordinator, client, home, device, dp_code, dp_info["properties"], dp_path
                        )
                    elif dp_code == "feed_abnormal":
                        number_entitiy = PhilipsPetsSeriesNumber(
                            coordinator, client, home, device, dp_code, dp_info["properties"], dp_path
                        )
                    else:
                        number_entitiy = PhilipsPetsSeriesNumber(
                            coordinator, client, home, device, dp_code, dp_info["properties"], dp_path, EntityCategory.CONFIG
                        )
                    numbers.append(number_entitiy)

    async_add_entities(numbers)

class PhilipsPetsSeriesNumber(PhilipsPetsSeriesEntity, NumberEntity):
    """Representation of a Philips Pets Series number entity for Integer datapoints."""

    def __init__(self, coordinator, client, home, device, dp_code, properties, dp_path, category=None):
        """Initialize the number entity."""
        super().__init__(coordinator, device, home)
        self._client = client
        self._dp_code = dp_code
        self._properties = properties
        self._dp_path = dp_path
        self._attr_unique_id = f"{device.id}_{dp_code}"
        self._attr_name = f"{dp_code.replace('_', ' ').title()} ({device.name})"
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
        current_value = settings.get(self._dp_code, self._attr_native_min_value)
        _LOGGER.debug(
            "Number Entity [%s]: current_value = %s",
            self._attr_name,
            current_value,
        )
        return current_value

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
        _LOGGER.info(settings)
        _LOGGER.info(self._dp_code)
        is_available = self._dp_code in settings
        if not is_available:
            _LOGGER.warning(
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
            await self.hass.async_add_executor_job(self._client.set_tuya_value, self._dp_code, int_value)
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error("Failed to set %s to %s: %s", self._attr_name, value, e)
