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
from .entity import PhilipsPetsSeriesEntity
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

    cameras = []
    for home in coordinator.data.get("homes", []):
        for device in coordinator.data.get("devices", []):
            cameras.append(PhilipsPetsSeriesCamera(coordinator, home, device, config_entry))

    async_add_entities(cameras)


class PhilipsPetsSeriesCamera(PhilipsPetsSeriesEntity, Camera):
    """Representation of a Philips Pets Series Camera."""

    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(self, coordinator: PhilipsPetsSeriesDataUpdateCoordinator, home, device, entry: ConfigEntry):
        """Initialize the camera."""
        PhilipsPetsSeriesEntity.__init__(self, coordinator, device, home)
        Camera.__init__(self)
        self._attr_unique_id = f"{device.id}_camera"
        self._attr_name = f"{device.name} Camera"
        self._attr_icon = "mdi:cctv"
        self._entry = entry
        
        # Check for Tuya credentials
        self._tuya_creds = {
             "device_id": self._entry.data.get("tuya_client_id"), # In config flow mapped to existing Tuya Client ID field? 
             # Wait, config_flow uses CONF_TUYA_CLIENT_ID which might not be device_id but Access ID.
             # But user investigation showed they likely put device ID there.
             "local_key": self._entry.data.get("tuya_local_key"),
             "ip": self._entry.data.get("tuya_ip"),
        }

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attrs = super().extra_state_attributes or {}
        # Expose Tuya details for easy go2rtc setup
        if self._tuya_creds["device_id"]:
             attrs["tuya_device_id"] = self._tuya_creds["device_id"]
        if self._tuya_creds["local_key"]:
             attrs["tuya_local_key"] = self._tuya_creds["local_key"]
        return attrs

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
        """Return the source of the stream."""
        # Check if go2rtc is running on localhost or configured
        # For now, we return None as we can't guarantee the stream URL without go2rtc.
        # But if the user manually configures go2rtc with the attributes we expose, 
        # they can override the stream_source via customization or we can look for a config option.
        
        # Placeholder: If the user adds a specific options entry, use it.
        if stream_url := self._entry.options.get("stream_url"):
            return stream_url
            
        return None
