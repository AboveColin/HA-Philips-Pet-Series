"""Firmware update entities.

Read-only by design.  Probing the Tuya upgrade endpoints with a Philips
third-party OAuth token returns PERMISSION_DENIED for
``thing.m.device.upgrade.info`` and ``.auto.switch.get``, so this integration
cannot start an update even when one is on offer.  An install button that always
fails is worse than no button, so the entity reports versions and leaves
installing to the Philips app.
"""

from __future__ import annotations

import logging

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN, PhilipsPetsSeriesDataUpdateCoordinator
from . import firmware
from .entity import PhilipsPetsSeriesEntity, iter_home_devices

_LOGGER = logging.getLogger(__name__)

# The modules a feeder can report, and how to label them.  "wifi" is always
# present; a feeder without a separate microcontroller never reports "mcu", and a
# permanently empty entity is worse than no entity.
_COMPONENTS = {
    "wifi": ("WiFi firmware", "mdi:wifi"),
    "mcu": ("MCU firmware", "mdi:chip"),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one update entity per firmware module the feeder reports."""
    coordinator: PhilipsPetsSeriesDataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]["coordinator"]

    entities = []
    for home, device in iter_home_devices(coordinator):
        for component in _COMPONENTS:
            if component == "mcu" and not firmware.has_ota_module(
                coordinator, device, "mcu"
            ):
                continue
            entities.append(
                PhilipsPetsSeriesFirmwareUpdate(coordinator, home, device, component)
            )

    async_add_entities(entities)


class PhilipsPetsSeriesFirmwareUpdate(PhilipsPetsSeriesEntity, UpdateEntity):
    """What a firmware module is running, and what Philips has on offer."""

    _attr_device_class = UpdateDeviceClass.FIRMWARE
    # Deliberately no UpdateEntityFeature.INSTALL; see the module docstring.
    _attr_supported_features = UpdateEntityFeature(0)

    def __init__(self, coordinator, home, device, component: str) -> None:
        """Initialise the update entity for one firmware module."""
        super().__init__(coordinator, device, home)
        self._component = component
        name, icon = _COMPONENTS[component]
        self._attr_unique_id = f"{device.id}_{component}_firmware_update"
        self._attr_name = name
        self._attr_icon = icon
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def installed_version(self) -> str | None:
        """The version the module is running now."""
        return firmware.installed_version(self.coordinator, self._device, self._component)

    @property
    def latest_version(self) -> str | None:
        """The offered version, or the installed one when nothing is on offer.

        Reporting None would render as "unknown" rather than "up to date", which
        reads as a fault on a feeder that is simply current.  Tuya publishes an
        offer only while ``upgradeStatus`` is non-zero, so no offer genuinely
        means there is nothing newer that we can see.
        """
        offered = firmware.offered_version(
            self.coordinator, self._device, self._component
        )
        return offered or self.installed_version

    @property
    def release_summary(self) -> str | None:
        """Say where an update has to be installed, since it cannot be here."""
        if not firmware.offered_version(
            self.coordinator, self._device, self._component
        ):
            return None
        return (
            "Philips does not let a third-party login start an update, so install "
            "this one from the Philips Pet Series app."
        )

    @property
    def extra_state_attributes(self):
        """The raw OTA record, for anyone wanting to see what Philips offered."""
        record, from_history = firmware.ota_record(
            self.coordinator, self._device.id, self._component
        )
        if not record:
            return None
        return {
            "upgrade_status": record.get("upgradeStatus"),
            "upgrade_type": record.get("upgradeType"),
            "file_size": record.get("fileSize"),
            "md5": record.get("md5"),
            # A signed package URL is short-lived, so it is worth knowing whether
            # this record is live or was kept from an earlier offer.
            "captured_from_history": from_history,
        }
