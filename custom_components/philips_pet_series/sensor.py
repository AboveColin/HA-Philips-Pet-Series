import base64
from datetime import datetime
import json

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorEntity,
    SensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

import logging

from petsseries.api import PetsSeriesClient

from . import DOMAIN, PhilipsPetsSeriesDataUpdateCoordinator
from .const import REMOVED_DP_SENSORS  # noqa: F401  (documented alongside _READ_ONLY_TUYA_DPS)
from .datapoints import datapoints
from .entity import PhilipsPetsSeriesEntity, iter_home_devices

_LOGGER = logging.getLogger(__name__)

# Home Assistant rejects states longer than this, so long raw payloads are
# truncated into the state and preserved in an attribute.
_MAX_STATE_LENGTH = 255

# Read-only datapoints worth surfacing, named from the device's own schema.
# Datapoints deliberately left out (see REMOVED_DP_SENSORS in const): command registers
# and packed integers the device never documents, which only ever produced an
# opaque number.
_READ_ONLY_TUYA_DPS = {
    # "grams per portion": the device's portion calibration, so
    # portions x this = the amount of food dispensed.
    "202": ("Portion size", "g"),
    # "feeding abnormality": the fault register the food/outlet problem
    # sensors use to decide whether a fault is still current.
    "255": ("Feeding fault", None),
    # "reported history data": a packed feeding record whose encoding Philips
    # does not publish.  Recorded history shows it does change around feeding
    # (observed 256/512/768, i.e. n << 8), so it is kept for anyone wanting to
    # decode it -- but disabled by default, since an opaque integer is not
    # useful on a dashboard.
    "206": ("Reported history data", None),
}

# Datapoints surfaced only for diagnosis; created disabled so they do not clutter
# the device page unless somebody deliberately turns them on.
_DISABLED_BY_DEFAULT_DPS = ("206",)

def _has_ota_module(coordinator, device, module: str) -> bool:
    """Whether the device's metadata reports an OTA module by this name."""
    definition = coordinator.data.get("device_definitions", {}).get(device.id)
    if not isinstance(definition, dict):
        return False
    ota_info = definition.get("otaInfo")
    if not isinstance(ota_info, dict):
        return False
    module_map = ota_info.get("otaModuleMap")
    if not isinstance(module_map, dict):
        return False
    entry = module_map.get(module)
    return isinstance(entry, dict) and bool(entry.get("verSw"))


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
    for home, device in iter_home_devices(coordinator):
        # Only offer an MCU version where the hardware reports one; feeders
        # without a separate microcontroller list a wireless module only, and a
        # permanently empty sensor is worse than no sensor.
        if _has_ota_module(coordinator, device, "mcu"):
            sensors.append(PhilipsPetsSeriesFirmwareSensor(coordinator, home, device, "mcu"))
        sensors.append(PhilipsPetsSeriesFirmwareSensor(coordinator, home, device, "wifi"))
        sensors.extend(
            PhilipsPetsSeriesRawDpSensor(coordinator, home, device, dp_id, name, unit)
            for dp_id, (name, unit) in _READ_ONLY_TUYA_DPS.items()
        )
        sensors.append(PhilipsPetsSeriesCameraOrientationSensor(coordinator, home, device))
        sensors.append(PhilipsPetsSeriesMotionSnapshotSensor(coordinator, home, device))
        for event_type_str in event_types_str:
            sensors.append(
                PhilipsPetsSeriesEventSensor(coordinator, home, device, event_type_str)
            )

    # Cloud DP status is available through the authenticated Philips/Tuya path;
    # a LAN TinyTuya client is optional.
    client: PetsSeriesClient = hass.data[DOMAIN][config_entry.entry_id]["client"]
    if client.tuya_client or getattr(client.auth, "id_token", None):
        for home, device in iter_home_devices(coordinator):
            sensors.append(
                PhilipsPetsSeriesTuyaStatusSensor(coordinator, home, device, client)
            )

    # Add Invites Sensor
    for home in coordinator.data.get("homes", []):
        sensors.append(PhilipsPetsSeriesInvitesSensor(coordinator, home))

    # Add Discovery Sensor
    sensors.append(PhilipsPetsSeriesDiscoverySensor(coordinator))

    async_add_entities(sensors)


class PhilipsPetsSeriesFirmwareSensor(PhilipsPetsSeriesEntity, SensorEntity):
    """Expose the MCU/WiFi versions reported by the Tuya device metadata."""

    def __init__(self, coordinator, home, device, component: str):
        super().__init__(coordinator, device, home)
        self._component = component
        self._attr_unique_id = f"{device.id}_{component}_firmware_version"
        self._attr_name = f"{component.upper()} firmware version"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_icon = "mdi:chip" if component == "mcu" else "mdi:wifi"

    def _device_definition(self) -> dict:
        """Tuya device metadata (``thing.m.device.get``) for this device."""
        definition = self.coordinator.data.get("device_definitions", {}).get(
            self._device.id
        )
        return definition if isinstance(definition, dict) else {}

    def _ota_module(self) -> dict:
        """Per-module OTA record for this component, when the device reports one.

        Devices expose ``otaInfo.otaModuleMap`` keyed by module name ("wifi",
        "mcu").  Feeders without a separate microcontroller only list "wifi",
        in which case there is genuinely no MCU version to report.
        """
        ota_info = self._device_definition().get("otaInfo")
        if not isinstance(ota_info, dict):
            return {}
        module_map = ota_info.get("otaModuleMap")
        if not isinstance(module_map, dict):
            return {}
        module = module_map.get(self._component)
        return module if isinstance(module, dict) else {}

    @property
    def native_value(self):
        ota_type = 9 if self._component == "mcu" else 0
        records = (
            self.coordinator.data.get("firmware_info", {}).get(self._device.id, [])
            + self.coordinator.data.get("product_firmware_info", {}).get(self._device.id, [])
        )
        if not records:
            records = self.coordinator.data.get("ota_history", {}).get(self._device.id, [])
        for record in records:
            try:
                if int(record.get("type", -1)) == ota_type:
                    version = record.get("currentVersion") or record.get("current_version")
                    if version:
                        return version
            except (TypeError, ValueError):
                continue
        # The OTA endpoints are frequently unauthorised for third-party logins,
        # so fall back to the version the device metadata reports directly.
        module_version = self._ota_module().get("verSw")
        if module_version:
            return module_version
        if self._component == "wifi":
            # ``verSw`` on the device record is the wireless module firmware,
            # which is the version the Philips app shows for the device.
            definition_version = self._device_definition().get("verSw")
            if definition_version:
                return definition_version
        value = getattr(self._device, f"{self._component}_version", None)
        if value:
            return value
        status = self.coordinator.data.get("settings", {}).get(self._device.id, {}).get("tuya_status", {})
        for key in (f"{self._component}Version", f"{self._component}_version", self._component):
            if status.get(key) is not None:
                return str(status[key])
        return None

    @property
    def extra_state_attributes(self):
        ota_type = 9 if self._component == "mcu" else 0
        records = (
            self.coordinator.data.get("firmware_info", {}).get(self._device.id, [])
            + self.coordinator.data.get("product_firmware_info", {}).get(self._device.id, [])
        )
        captured = not records
        if not records:
            records = self.coordinator.data.get("ota_history", {}).get(self._device.id, [])
        for record in records:
            try:
                if int(record.get("type", -1)) == ota_type:
                    return {
                        "ota_type": record.get("type"),
                        "version": record.get("version"),
                        "current_version": record.get("currentVersion") or record.get("current_version"),
                        "available_version": record.get("version"),
                        "upgrade_status": record.get("upgradeStatus"),
                        "upgrade_type": record.get("upgradeType"),
                        "upgrade_mode": record.get("upgradeMode"),
                        "can_upgrade": record.get("canUpgrade"),
                        "url": record.get("url"),
                        "file_size": record.get("fileSize"),
                        "md5": record.get("md5"),
                        "sign": record.get("sign"),
                        "hmac": record.get("hmac"),
                        "file_path": record.get("filePath"),
                        "diff_ota": record.get("diffOta"),
                        "update_available": record.get("upgradeStatus") == 1,
                        "captured_from_history": captured,
                    }
            except (TypeError, ValueError):
                continue
        return None


class PhilipsPetsSeriesRawDpSensor(PhilipsPetsSeriesEntity, SensorEntity):
    """Expose a read-only Tuya datapoint without allowing control."""

    def __init__(self, coordinator, home, device, dp_id: str, name: str, unit: str | None) -> None:
        super().__init__(coordinator, device, home)
        self._dp_id = dp_id
        self._attr_unique_id = f"{device.id}_tuya_dp_{dp_id}"
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_icon = "mdi:scale" if unit == "g" else "mdi:alert-circle-outline"
        if dp_id in _DISABLED_BY_DEFAULT_DPS:
            self._attr_entity_registry_enabled_default = False
        self._scale = int(
            (datapoints.get(dp_id, {}).get("properties") or {}).get("scale") or 0
        )

    @property
    def _raw_value(self):
        value = (
            self.coordinator.data.get("settings", {})
            .get(self._device.id, {})
            .get("tuya_status", {})
            .get(self._dp_id)
        )
        # Several datapoints report an empty string when they hold nothing;
        # that is an absent value, not a state of "".
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def native_value(self):
        value = self._raw_value
        if value is None:
            return None
        # Tuya transmits fixed-point integers: the datapoint's scale says how
        # many decimal places the raw value carries.
        if self._scale and isinstance(value, (int, float)) and not isinstance(value, bool):
            return value / (10 ** self._scale)
        if not isinstance(value, (str, int, float)):
            value = str(value)
        # Some datapoints carry base64 blobs (snapshots, history, voice files)
        # that exceed Home Assistant's 255-character state limit, which would
        # make the whole entity fail to update.  Keep the state short and put
        # the full payload in an attribute.
        if isinstance(value, str) and len(value) > _MAX_STATE_LENGTH:
            return value[: _MAX_STATE_LENGTH - 1] + "…"
        return value

    @property
    def available(self) -> bool:
        return super().available and self._raw_value is not None

    @property
    def extra_state_attributes(self):
        attributes = {"dp_id": self._dp_id, "read_only": True}
        value = self._raw_value
        if isinstance(value, str) and len(value) > _MAX_STATE_LENGTH:
            attributes["full_value"] = value
            attributes["truncated"] = True
        return attributes


class PhilipsPetsSeriesCameraOrientationSensor(PhilipsPetsSeriesEntity, SensorEntity):
    """Expose the camera transform reported by Tuya DP 241."""

    def __init__(self, coordinator, home, device) -> None:
        super().__init__(coordinator, device, home)
        self._attr_unique_id = f"{device.id}_camera_orientation"
        self._attr_name = "Camera orientation"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_icon = "mdi:rotate-right"

    @property
    def native_value(self):
        return (
            self.coordinator.data.get("settings", {})
            .get(self._device.id, {})
            .get("tuya_status", {})
            .get("241")
        )

    @property
    def available(self) -> bool:
        return super().available and self.native_value is not None


class PhilipsPetsSeriesMotionSnapshotSensor(PhilipsPetsSeriesEntity, SensorEntity):
    """Expose safe metadata from Tuya DP 212 motion-image notifications."""

    def __init__(self, coordinator, home, device) -> None:
        super().__init__(coordinator, device, home)
        self._attr_unique_id = f"{device.id}_motion_snapshot_metadata"
        self._attr_name = "Last motion snapshot metadata"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_icon = "mdi:camera-outline"

    @property
    def _metadata(self) -> dict:
        value = (
            self.coordinator.data.get("settings", {})
            .get(self._device.id, {})
            .get("tuya_status", {})
            .get("212")
        )
        if not isinstance(value, str) or not value:
            return {}
        try:
            return json.loads(base64.b64decode(value).decode())
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return {}

    @property
    def native_value(self):
        timestamp = self._metadata.get("time")
        return str(timestamp) if timestamp is not None else None

    @property
    def available(self) -> bool:
        return super().available and bool(self._metadata)

    @property
    def extra_state_attributes(self):
        metadata = self._metadata
        if not metadata:
            return None
        return {
            "version": metadata.get("v"),
            "command": metadata.get("cmd"),
            "media_type": metadata.get("type"),
            "alarm": metadata.get("alarm"),
            "timestamp": metadata.get("time"),
        }


class PhilipsPetsSeriesEventSensor(PhilipsPetsSeriesEntity, RestoreSensor):
    """When this device last raised a given event.

    Philips only serves a bounded slice of event history, so an event older than
    that window is absent from the API even though it certainly happened.  The
    last known timestamp is therefore restored across restarts and only ever
    moves forward, instead of reverting to "unknown" whenever the event ages out
    of the query window.
    """

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
        self._restored_value: datetime | None = None

    async def async_added_to_hass(self) -> None:
        """Restore the last known timestamp before the first refresh."""
        await super().async_added_to_hass()
        last_data = await self.async_get_last_sensor_data()
        if last_data is not None and isinstance(last_data.native_value, datetime):
            self._restored_value = last_data.native_value

    def _latest_event(self):
        """Return this device's newest event of this type, if any.

        The coordinator indexes events per home, so events raised by other
        devices in the same home must be filtered out -- otherwise this sensor
        reports another feeder's timestamp, name and thumbnail.
        """
        key = f"{self._home.id}_{self._event_type}"
        events = self.coordinator.data.get("events_by_home_and_type", {}).get(key, [])
        mine = [
            event
            for event in events
            if getattr(event, "device_id", None) is None
            or str(event.device_id) == str(self._device.id)
        ]
        if not mine:
            return None
        return max(
            mine,
            key=lambda event: dt_util.parse_datetime(event.time) or dt_util.utcnow(),
        )

    @property
    def native_value(self):
        latest_event = self._latest_event()
        parsed_time = None
        if latest_event is not None:
            parsed_time = dt_util.parse_datetime(latest_event.time)
            if parsed_time is None:
                _LOGGER.warning("Failed to parse event time for %s", self._event_type)
        # Never regress: an event dropping out of the API's history window does
        # not mean it stopped having happened.
        candidates = [
            value for value in (parsed_time, self._restored_value) if value is not None
        ]
        if not candidates:
            return None
        newest = max(candidates)
        self._restored_value = newest
        # Return the datetime itself: HA normalises it for TIMESTAMP sensors.
        return newest

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = {}
        latest_event = self._latest_event()
        if latest_event is not None:
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
    def device_info(self):
        """Represent the Philips home even when it has no devices."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"home_{self.home.id}")},
            name=self.home.name,
            manufacturer="Philips",
            model="Pet Series Home",
        )

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


class PhilipsPetsSeriesTuyaStatusSensor(PhilipsPetsSeriesEntity, SensorEntity):
    """Diagnostic dump of the datapoints the Tuya cloud returned.

    Kept for troubleshooting -- its attributes carry the raw and normalised
    datapoint maps.  Connectivity itself is better read from the
    ``tuya_cloud_connected`` binary sensor; this entity exists for the payload.
    """

    def __init__(
        self,
        coordinator: PhilipsPetsSeriesDataUpdateCoordinator,
        home,
        device,
        client: PetsSeriesClient,
    ):
        """Initialize the Tuya status sensor."""
        # Register against the device like every other entity; subclassing the
        # coordinator entity directly left this orphaned from its device.
        super().__init__(coordinator, device, home)
        self.home = home
        self.device = device
        self.client = client
        self._attr_unique_id = f"{device.id}_tuya_status"
        self._attr_name = "Tuya datapoints"
        self._attr_icon = "mdi:cloud"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def state(self):
        """Return whether the authenticated Tuya cloud returned device DPs."""
        status = self._status
        return "online" if status else "unavailable"

    @property
    def _status(self):
        return (
            self.coordinator.data.get("settings", {})
            .get(self.device.id, {})
            .get("tuya_status", {})
        )

    @property
    def extra_state_attributes(self):
        """Return cloud DPs without credential material."""
        status = self._status
        if not isinstance(status, dict):
            return {}
        return {
            "raw_dps": {key: value for key, value in status.items() if str(key).isdigit()},
            "normalized_dps": {
                key: value for key, value in status.items() if not str(key).isdigit()
            },
        }

    @property
    def available(self):
        """Return if the sensor is available."""
        return (
            super().available
            and self.coordinator.last_update_success
            and bool(self._status)
        )


class PhilipsPetsSeriesDiscoverySensor(CoordinatorEntity, SensorEntity):
    """Representation of the Philips Pets Series Discovery (Version) Sensor."""

    def __init__(self, coordinator):
        """Initialize the discovery sensor."""
        super().__init__(coordinator)
        # Entry-scoped: a bare constant collides when a second account is
        # configured, and HA then drops the duplicate entity.
        entry_id = getattr(getattr(coordinator, "config_entry", None), "entry_id", None)
        self._attr_unique_id = (
            f"{entry_id}_api_version" if entry_id else "philips_pet_series_api_version"
        )
        self._attr_name = "Philips Pet Series Cloud Version"
        self._attr_icon = "mdi:cloud-check"

    @property
    def state(self):
        """Return the current android version as a proxy for API version."""
        config = self.coordinator.data.get("base_data", {}).get("discovery_config")
        if config and config.android_release:
            # Report unknown rather than a literal "Unknown"/"" so templates can
            # test the state properly.
            return config.android_release.current_version or None
        return None

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
