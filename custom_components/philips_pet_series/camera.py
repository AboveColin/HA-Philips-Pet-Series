from __future__ import annotations

from typing import Optional

from homeassistant.components.camera import Camera, CameraEntityFeature
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
    """Set up the Philips Pets Series cameras."""
    coordinator: PhilipsPetsSeriesDataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]["coordinator"]
    client = hass.data[DOMAIN][config_entry.entry_id]["client"]
    bridge = hass.data[DOMAIN][config_entry.entry_id]["bridge"]

    # The integration supervises the bundled pure-Go Tuya P2P->RTSP bridge.
    # No stream URL or local Tuya credential options are required.
    cameras = []
    for home, device in iter_home_devices(coordinator):
        cameras.append(
            PhilipsPetsSeriesCamera(coordinator, home, device, config_entry, bridge)
        )

    async_add_entities(cameras)


class PhilipsPetsSeriesCamera(PhilipsPetsSeriesEntity, Camera):
    """Representation of a Philips Pets Series Camera.

    The bundled bridge turns the feeder's proprietary Tuya media transport into
    an internal RTSP source. Motion snapshots remain available as the still
    image fallback.
    """

    def __init__(
        self,
        coordinator: PhilipsPetsSeriesDataUpdateCoordinator,
        home,
        device,
        entry: ConfigEntry,
        bridge,
    ):
        """Initialize the camera."""
        PhilipsPetsSeriesEntity.__init__(self, coordinator, device, home)
        Camera.__init__(self)
        self._attr_unique_id = f"{device.id}_camera"
        self._attr_name = f"{device.name} Camera"
        self._attr_icon = "mdi:cctv"
        self._entry = entry
        self._bridge = bridge
        self._stream_url = self._bridge.stream_url(device)
        if self._stream_url:
            self._attr_supported_features = CameraEntityFeature.STREAM

    def _get_latest_event(self):
        key = f"{self._home.id}_motion_detected"
        events = self.coordinator.data.get("events_by_home_and_type", {}).get(key, [])
        if events:
            return events[0]
        return None

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return a still image response from the camera."""
        # Use the latest motion event image as the still image
        latest_event = self._get_latest_event()
        if not latest_event:
            return None

        url = latest_event.thumbnail_url
        key = latest_event.thumbnail_key

        if not url or not key:
            return None

        session = async_get_clientsession(self.hass)
        try:
            async with session.get(url) as response:
                response.raise_for_status()
                content = await response.read()

            return await self.hass.async_add_executor_job(decrypt_image, content, key)

        except Exception as e:
            _LOGGER.error(f"Error fetching/decrypting camera image: {e}")
            return None

    async def stream_source(self) -> str | None:
        """Return the integration-managed RTSP stream URL."""
        return self._stream_url
