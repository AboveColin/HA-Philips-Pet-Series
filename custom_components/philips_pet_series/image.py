from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

import logging
from . import DOMAIN, PhilipsPetsSeriesDataUpdateCoordinator
from .entity import PhilipsPetsSeriesEntity, iter_home_devices
from petsseries.crypto import decrypt_image

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Philips Pets Series images."""
    coordinator: PhilipsPetsSeriesDataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]["coordinator"]

    images = []
    for home, device in iter_home_devices(coordinator):
        images.append(PhilipsPetsSeriesMotionImage(coordinator, home, device))

    async_add_entities(images)


class PhilipsPetsSeriesMotionImage(PhilipsPetsSeriesEntity, ImageEntity):
    """Representation of a Philips Pets Series Motion Snapshot."""

    def __init__(self, coordinator: PhilipsPetsSeriesDataUpdateCoordinator, home, device):
        """Initialize the image entity."""
        PhilipsPetsSeriesEntity.__init__(self, coordinator, device, home)
        ImageEntity.__init__(self, coordinator.hass)
        self._attr_unique_id = f"{device.id}_last_motion_snapshot"
        self._attr_name = f"{device.name} Last Motion Snapshot"
        self._attr_icon = "mdi:camera"

    @property
    def image_last_updated(self):
        """The time when the image was last updated."""
        latest_event = self._get_latest_event()
        if latest_event:
             return dt_util.parse_datetime(latest_event.time)
        return None

    @property
    def available(self) -> bool:
        """Only report available while there is a snapshot to serve."""
        return super().available and self._get_latest_event() is not None

    def _get_latest_event(self):
        """Return this device's newest motion event, if any.

        Events are indexed per home, so entries from other devices in the same
        home have to be filtered out -- otherwise this entity would serve
        another camera's snapshot.  The API does not guarantee ordering, so pick
        the newest explicitly instead of trusting the first element.
        """
        key = f"{self._home.id}_motion_detected"
        events = self.coordinator.data.get("events_by_home_and_type", {}).get(key, [])
        mine = [
            event
            for event in events
            if getattr(event, "device_id", None) is None
            or str(event.device_id) == str(self._device.id)
        ]
        if not mine:
            return None
        return max(mine, key=lambda event: event.time or "")

    async def async_image(self) -> bytes | None:
        """Fetch and decrypt the image."""
        latest_event = self._get_latest_event()
        if not latest_event:
            return None

        url = latest_event.thumbnail_url
        key = latest_event.thumbnail_key

        if not url or not key:
            return None

        session = async_get_clientsession(self.hass)
        try:
            # Fetch the encrypted image
            async with session.get(url) as response:
                response.raise_for_status()
                content = await response.read()

            # Decrypt the image
            # Run in executor to avoid blocking parsing
            return await self.hass.async_add_executor_job(decrypt_image, content, key)

        except Exception as e:
            _LOGGER.error(f"Error fetching/decrypting image: {e}")
            return None
