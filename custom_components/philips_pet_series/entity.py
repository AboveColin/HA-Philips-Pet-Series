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
        # Try to find firmware version and model
        sw_version = self._device.product_id
        model = self._device.product_ctn
        
        # If we have tuya status, we might find version there 
        # (datapoint logic required but keeping broad here)
        
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
