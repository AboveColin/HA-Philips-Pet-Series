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

    @property
    def device_info(self):
        """Return device information about this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._device.id)},
            name=self._device.name,
            manufacturer="Philips",
            model=self._device.product_ctn,
            sw_version=self._device.product_id,
            via_device=(DOMAIN, self._home.id),
            hw_version=self._device.product_ctn,
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success
