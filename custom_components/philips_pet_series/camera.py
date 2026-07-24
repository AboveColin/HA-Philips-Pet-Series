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
from .bridge import CAMERA_MODE_DISABLED
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
        # A session is minted on demand, so advertise streaming support unless
        # the camera bridge is switched off entirely.
        if bridge.camera_mode != CAMERA_MODE_DISABLED:
            self._attr_supported_features = CameraEntityFeature.STREAM

    @property
    def is_streaming(self) -> bool:
        """Whether a live camera session is currently held for this device.

        Without this the entity reports "idle" permanently, because nothing else
        ever sets the flag.  Tracking the bridge makes the state meaningful: it
        shows when the feeder's single live session is actually in use.
        """
        bridge = self._bridge.processes.get(str(self._device.id))
        return bridge is not None and bridge.process.returncode is None

    def _get_latest_event(self):
        """Return this device's most recent motion event, if any.

        The coordinator indexes events per home, so entries belonging to other
        devices in the same home have to be filtered out, and the newest event
        picked explicitly rather than assuming the API returns them sorted.
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
        """Return the integration-managed RTSP stream URL.

        Home Assistant calls this each time a viewer needs the stream, which
        doubles as the keep-alive for an on-demand P2P session.
        """
        return await self._bridge.async_get_stream_url(self._device)
