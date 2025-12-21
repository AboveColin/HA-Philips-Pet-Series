from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

import logging

from petsseries.api import PetsSeriesClient

from . import DOMAIN, PhilipsPetsSeriesDataUpdateCoordinator
from .entity import PhilipsPetsSeriesEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Philips Pets Series sensors."""
    coordinator: PhilipsPetsSeriesDataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]["coordinator"]

    event_types = coordinator.data.get("event_types", [])
    meals = coordinator.data.get("meals", [])

    # Convert event_types to strings if they are objects
    event_types_str = []
    for event_type in event_types:
        if isinstance(event_type, str):
            event_types_str.append(event_type)
        elif hasattr(event_type, "value"):
            event_types_str.append(str(event_type.value))
        else:
            event_types_str.append(str(event_type))

    sensors = []
    for home in coordinator.data.get("homes", []):
        for device in coordinator.data.get("devices", []):
            for event_type_str in event_types_str:
                sensors.append(
                    PhilipsPetsSeriesEventSensor(coordinator, home, device, event_type_str)
                )

        for meal in meals:
            sensors.append(PhilipsPetsSeriesMealSensor(coordinator, meal))

    # If TuyaClient is initialized, add Tuya-related sensors
    client: PetsSeriesClient = hass.data[DOMAIN][config_entry.entry_id]["client"]
    if client.tuya_client:
        for home in coordinator.data.get("homes", []):
            for device in coordinator.data.get("devices", []):
                sensors.append(
                    PhilipsPetsSeriesTuyaStatusSensor(coordinator, home, device, client)
                )

    # Add Invites Sensor
    for home in coordinator.data.get("homes", []):
        sensors.append(PhilipsPetsSeriesInvitesSensor(coordinator, home))

    # Add Discovery Sensor
    sensors.append(PhilipsPetsSeriesDiscoverySensor(coordinator))

    async_add_entities(sensors)


class PhilipsPetsSeriesEventSensor(PhilipsPetsSeriesEntity, SensorEntity):
    """Representation of a Philips Pets Series event sensor."""

    def __init__(
        self,
        coordinator: PhilipsPetsSeriesDataUpdateCoordinator,
        home,
        device,
        event_type: str,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, device, home)
        self._event_type = event_type
        self._attr_unique_id = f"{device.id}_last_{self._event_type}_event"

        self._attr_name = f"Last {self._event_type.replace('eventtype.', ' ').replace('_', ' ').title()} Event"

        self._attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def state(self):
        key = f"{self._home.id}_{self._event_type}"
        events = self.coordinator.data.get("events_by_home_and_type", {}).get(key, [])
        if events:
            latest_event = events[0]
            parsed_time = dt_util.parse_datetime(latest_event.time)
            if parsed_time:
                return parsed_time.isoformat()
            else:
                _LOGGER.error(f"Failed to parse time: {latest_event.time}")
        else:
            self._attr_device_class = None
            return ">24 hours ago"

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = {}
        key = f"{self._home.id}_{self._event_type}"
        events = self.coordinator.data.get("events_by_home_and_type", {}).get(key, [])
        if events:
            latest_event = events[0]
            _LOGGER.debug(f"Latest event: {latest_event}")
            parsed_time = dt_util.parse_datetime(latest_event.time)
            attributes["source"] = latest_event.source
            attributes["event_id"] = latest_event.id
            attributes["original_time"] = (
                latest_event.time
            )
            if parsed_time:
                attributes["timestamp"] = parsed_time.timestamp()
            if latest_event.type == "motion_detected":
                attributes.update(
                    {
                        "device_name": latest_event.device_name,
                        "thumbnail_url": latest_event.thumbnail_url,
                    }
                )
            elif latest_event.type == "meal_dispensed":
                attributes.update(
                    {
                        "meal_name": latest_event.meal_name,
                        "meal_amount": latest_event.meal_amount,
                    }
                )
            elif latest_event.type == "meal_upcoming":
                attributes.update(
                    {
                        "meal_name": latest_event.meal_name,
                        "meal_amount": latest_event.meal_amount,
                    }
                )
            elif latest_event.type == "food_level_low":
                attributes.update(
                    {
                        "device_name": latest_event.device_name,
                        "product_ctn": latest_event.product_ctn,
                    }
                )
        return attributes

    @property
    def icon(self):
        """Return the icon to use in the frontend based on event type."""
        icon_map = {
            "motion_detected": "mdi:motion-sensor",
            "meal_dispensed": "mdi:food",
            "meal_upcoming": "mdi:food",
            "food_level_low": "mdi:alert",
            "meal_enabled": "mdi:check-circle",
            "filter_replacement_due": "mdi:filter",
            "food_outlet_stuck": "mdi:alert-circle",
            "device_offline": "mdi:power-plug-off",
            "device_online": "mdi:power-plug",
        }
        return icon_map.get(self._event_type, "mdi:information")

    @property
    def available(self):
        """Return if the sensor is available."""
        return super().available and self.coordinator.last_update_success

    async def async_update(self):
        """Update the sensor state."""
        await self.coordinator.async_request_refresh()


class PhilipsPetsSeriesMealSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Philips Pets Series Meal Sensor."""

    def __init__(self, coordinator, meal):
        """Initialize the meal sensor."""
        super().__init__(coordinator)
        self.meal = meal
        self._attr_unique_id = f"meal_{meal.id}"
        self._attr_name = meal.name
        self._attr_icon = "mdi:food"

    @property
    def device_info(self):
        """Return device information."""
        # Find the device this meal belongs to
        device = next(
            (d for d in self.coordinator.data.get("devices", []) if d.id == self.meal.device_id),
            None
        )
        
        identifiers = {(DOMAIN, self.meal.device_id)}
        
        # If we found the device, we can try to find the home it belongs to for via_device
        # But efficiently, we just need to link to the device ID.
        # Home Assistant links entities to devices via identifiers.
        
        if device:
             return DeviceInfo(
                identifiers=identifiers,
                name=device.name,
                manufacturer="Philips",
                model=device.product_ctn,
                sw_version=device.product_id,
                # via_device is optional if we share identifiers with the main device entity
            )
        
        return DeviceInfo(
            identifiers=identifiers,
            name=f"Device {self.meal.device_id}",
            manufacturer="Philips",
        )

    @property
    def state(self):
        """Return the next scheduled time of the meal."""
        return self.meal.feed_time

    @property
    def extra_state_attributes(self):
        """Return extra attributes of the meal."""
        return {
            "portion_amount": self.meal.portion_amount,
            "repeat_days": self.meal.repeat_days,
            "device_id": self.meal.device_id,
            "enabled": self.meal.enabled,
        }


class PhilipsPetsSeriesInvitesSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Philips Pets Series Invites Sensor."""

    def __init__(self, coordinator: PhilipsPetsSeriesDataUpdateCoordinator, home):
        """Initialize the invites sensor."""
        super().__init__(coordinator)
        self.home = home
        self._attr_unique_id = f"home_{home.id}_invites"
        self._attr_name = f"{home.name} Invites"
        self._attr_icon = "mdi:account-plus"

    @property
    def state(self):
        """Return the number of invites."""
        invites = self.coordinator.data.get("invites", {}).get(self.home.id, [])
        return len(invites)

    @property
    def extra_state_attributes(self):
        """Return extra attributes."""
        invites = self.coordinator.data.get("invites", {}).get(self.home.id, [])
        return {
            "invites": [
                {
                    "email": i.email,
                    "label": i.label,
                    "role": i.role.value,
                    "status": i.status.value,
                    "token": i.id, # Using ID as token or ID
                }
                for i in invites
            ]
        }

    @property
    def available(self):
        """Return if the sensor is available."""
        return super().available and self.coordinator.last_update_success


class PhilipsPetsSeriesTuyaStatusSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Philips Pets Series Tuya Status Sensor."""

    def __init__(
        self,
        coordinator: PhilipsPetsSeriesDataUpdateCoordinator,
        home,
        device,
        client: PetsSeriesClient,
    ):
        """Initialize the Tuya status sensor."""
        super().__init__(coordinator)
        self.home = home
        self.device = device
        self.client = client
        self._attr_unique_id = f"{device.id}_tuya_status"
        self._attr_name = f"{device.name} Tuya Status"
        self._attr_icon = "mdi:cloud"

    @property
    def state(self):
        """Return the Tuya device status."""
        # Fix logic to get status from correct path if needed
        # Assuming coordinator data structure is fixed or using base_data
        base_data = self.coordinator.data.get("base_data", {})
        tuya_status = base_data.get("tuya_status")
        if tuya_status:
            return tuya_status.get("status")
        return None

    @property
    def extra_state_attributes(self):
        """Return Tuya device attributes."""
        base_data = self.coordinator.data.get("base_data", {})
        tuya_status = base_data.get("tuya_status")
        if tuya_status:
            return tuya_status
        return {}
    
    @property
    def available(self):
        """Return if the sensor is available."""
        return (
            super().available
            and self.coordinator.last_update_success
            and self.coordinator.data.get("base_data", {}).get("tuya_status") is not None
        )


class PhilipsPetsSeriesDiscoverySensor(CoordinatorEntity, SensorEntity):
    """Representation of the Philips Pets Series Discovery (Version) Sensor."""

    def __init__(self, coordinator):
        """Initialize the discovery sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = "philips_pet_series_api_version"
        self._attr_name = "Philips Pet Series Cloud Version"
        self._attr_icon = "mdi:cloud-check"

    @property
    def state(self):
        """Return the current android version as a proxy for API version."""
        config = self.coordinator.data.get("base_data", {}).get("discovery_config")
        if config and config.android_release:
            return config.android_release.current_version
        return "Unknown"

    @property
    def extra_state_attributes(self):
        """Return extra attributes."""
        config = self.coordinator.data.get("base_data", {}).get("discovery_config")
        if config:
            return {
                "api_url": config.api_url,
                "consumer_url": config.consumer_url,
                "ios_version": config.ios_release.current_version if config.ios_release else None,
                "min_android_version": config.android_release.min_version if config.android_release else None,
            }
        return {}
