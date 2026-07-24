"""Base entity for Philips Pets Series integration."""

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from . import PhilipsPetsSeriesDataUpdateCoordinator


class PhilipsPetsSeriesEntity(CoordinatorEntity):
    """Base entity class for Philips Pets Series devices."""

    def __init__(
        self, coordinator: PhilipsPetsSeriesDataUpdateCoordinator, device, home
    ):
        """Initialize the entity."""
        super().__init__(coordinator)
        self._device = device
        self._home = home

    def _definition_version(self):
        """Firmware version from the Tuya device record, when available."""
        data = getattr(self.coordinator, "data", None) or {}
        definition = data.get("device_definitions", {}).get(self._device.id)
        if not isinstance(definition, dict):
            return None
        ota_info = definition.get("otaInfo")
        if isinstance(ota_info, dict):
            module_map = ota_info.get("otaModuleMap")
            if isinstance(module_map, dict):
                wifi = module_map.get("wifi")
                if isinstance(wifi, dict) and wifi.get("verSw"):
                    return wifi["verSw"]
        return definition.get("verSw")

    @property
    def device_info(self):
        """Return device information about this entity."""
        # The app treats the WiFi firmware as the primary device version;
        # expose it in the registry while dedicated MCU/WiFi sensors retain
        # both component values.  The OTA endpoints that would populate
        # wifi_version are often unauthorised for third-party logins, so fall
        # back to the version reported by the Tuya device record itself.
        sw_version = (
            getattr(self._device, "wifi_version", None)
            or getattr(self._device, "mcu_version", None)
            or self._definition_version()
            or self._device.product_id
        )
        model = self._device.product_ctn

        return DeviceInfo(
            identifiers={(DOMAIN, self._device.id)},
            name=self._device.name,
            manufacturer="Philips",
            model=model,
            sw_version=sw_version,
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success


def iter_home_devices(coordinator):
    """Yield each API home/device relationship exactly once."""
    homes = {home.id: home for home in coordinator.data.get("homes", [])}
    for home_id, devices in coordinator.data.get("home_devices", {}).items():
        home = homes.get(home_id)
        if home is not None:
            yield from ((home, device) for device in devices)
