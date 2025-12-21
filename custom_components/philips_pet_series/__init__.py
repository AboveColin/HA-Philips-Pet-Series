from __future__ import annotations

import asyncio
import datetime as dt
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

try:
    import petsseries
except ImportError as e:
    _LOGGER.error("Failed to import petsseries module: %s", e)
    raise

from petsseries.models import Event

from petsseries import PetsSeriesClient

from .const import DOMAIN

PLATFORMS = [
    Platform.SWITCH,
    Platform.SENSOR,
    Platform.SELECT,
    Platform.NUMBER,
    Platform.BUTTON,
    Platform.CALENDAR,
    Platform.IMAGE,
    Platform.CAMERA,
]

SCAN_INTERVAL = timedelta(minutes=5)


class PhilipsPetsSeriesDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator to fetch data for Philips Pets Series sensors."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: PetsSeriesClient,
        delay_between_calls: float = 1,
    ):
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self._client = client
        self.delay_between_calls = delay_between_calls

    async def _async_update_data(self):
        """Fetch data from API."""
        try:
            homes = await self._client.get_homes()
            devices = []
            meals = []
            events_by_home_and_type = {}
            invites_by_home = {}
            settings = {}
            full_settings = {}
            event_types = Event.get_event_types()
            now = dt_util.now()
            from_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            to_date = from_date + timedelta(days=1)

            for home in homes:
                try:
                    home_devices = await self._client.get_devices(home)
                    devices.extend(home_devices)
                    _LOGGER.debug("Fetched %d devices for home %s", len(home_devices), home.id)
                except Exception as e:
                    _LOGGER.warning("Failed to fetch devices for home %s: %s", home.id, e)
                    continue

                await asyncio.sleep(self.delay_between_calls)

                # Fetch events
                for event_type in event_types:
                    try:
                        home_events = await self._client.events.get_events(
                            home,
                            from_date=from_date,
                            to_date=to_date,
                            types=str(event_type),
                        )
                        event_type_str = (
                            event_type
                            if isinstance(event_type, str)
                            else (
                                event_type.value
                                if hasattr(event_type, "value")
                                else str(event_type)
                            )
                        )

                        key = f"{home.id}_{event_type_str}"
                        events_by_home_and_type[key] = home_events
                    except Exception as e:
                        _LOGGER.warning("Failed to fetch events %s for home %s: %s", event_type, home.id, e)

                    await asyncio.sleep(self.delay_between_calls)

                # Fetch settings for devices
                for device in home_devices:
                    try:
                        device_settings = await self._client.get_settings(home, device.id)
                        settings[device.id] = device_settings
                    except Exception as e:
                        _LOGGER.warning("Failed to fetch settings for device %s: %s", device.id, e)
                        settings[device.id] = {}

                    # Fetch full settings
                    try:
                        device_full_settings = await self._client.devices_manager.get_device_settings(home, device)
                        full_settings[device.id] = device_full_settings
                    except Exception as e:
                        _LOGGER.warning("Failed to fetch full settings for device %s: %s", device.id, e)

                    # Fetch Tuya status if available
                    if self._client.tuya_client:
                        try:
                            tuya_status = await asyncio.to_thread(
                                self._client.get_tuya_status
                            )
                            if device.id in settings:
                                settings[device.id]["tuya_status"] = tuya_status
                        except Exception as e:
                            _LOGGER.warning("Failed to fetch Tuya status for device %s: %s", device.id, e)
                            if device.id in settings:
                                settings[device.id]["tuya_status"] = None
                    elif device.id in settings:
                        settings[device.id]["tuya_status"] = None

                    await asyncio.sleep(self.delay_between_calls)

                # Fetch meals
                try:
                    home_meals = await self._client.meals.get_meals(home)
                    meals.extend(home_meals)
                    _LOGGER.debug("Fetched %d meals for home %s", len(home_meals), home.id)
                except Exception as e:
                    _LOGGER.warning("Failed to fetch meals for home %s: %s", home.id, e)

                # Fetch invites
                try:
                    home_invites = await self._client.homes_manager.get_invites(home)
                    invites_by_home[home.id] = home_invites
                    _LOGGER.debug("Fetched %d invites for home %s", len(home_invites), home.id)
                except Exception as e:
                    _LOGGER.warning("Failed to fetch invites for home %s: %s", home.id, e)

                await asyncio.sleep(self.delay_between_calls)

            base_data = {}
            if self._client.tuya_client:
                try:
                    base_data["tuya_status"] = await asyncio.to_thread(self._client.get_tuya_status)
                except Exception as e:
                    _LOGGER.warning("Failed to fetch base Tuya status: %s", e)
                    base_data["tuya_status"] = None
            else:
                base_data["tuya_status"] = None

            # Fetch discovery config
            try:
                discovery_config = await self._client.discovery_manager.get_discovery_config()
                base_data["discovery_config"] = discovery_config
            except Exception as e:
                _LOGGER.warning("Failed to fetch discovery config: %s", e)
                base_data["discovery_config"] = None

            return {
                "homes": homes,
                "devices": devices,
                "meals": meals,
                "invites": invites_by_home,
                "events_by_home_and_type": events_by_home_and_type,
                "event_types": event_types,
                "settings": settings,
                "full_settings": full_settings,
                "base_data": base_data,
            }
        except ConfigEntryAuthFailed:
            # Re-raise auth failures so they can be handled properly
            raise
        except Exception as err:
            _LOGGER.exception("Error communicating with API: %s", err)
            raise UpdateFailed(f"Error communicating with API: {err}") from err


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Philips Pets Series from a config entry."""
    # Merge options into data for backward compatibility
    data = {**entry.data, **entry.options}
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")

    tuya_credentials = None
    if all(
        key in data and data[key]
        for key in ("tuya_client_id", "tuya_ip", "tuya_local_key")
    ):
        tuya_credentials = {
            "client_id": data["tuya_client_id"],
            "ip": data["tuya_ip"],
            "local_key": data["tuya_local_key"],
            "version": data.get("tuya_version", 3.4),
        }

    async def save_tokens_callback(access_token: str, refresh_token: str) -> None:
        """Save tokens to config entry."""
        _LOGGER.debug("Saving new tokens to config entry")
        hass.config_entries.async_update_entry(
            entry,
            data={
                **entry.data,
                "access_token": access_token,
                "refresh_token": refresh_token,
            },
        )

    client = PetsSeriesClient(
        token_file=None,
        access_token=access_token,
        refresh_token=refresh_token,
        tuya_credentials=tuya_credentials,
        token_save_callback=save_tokens_callback,
    )
    try:
        await client.initialize()
    except Exception as e:
        _LOGGER.error(f"Error initializing Philips Pets Series client: {e}")
        if "invalid_client" in str(e):
            raise ConfigEntryAuthFailed(
                "Invalid client credentials. Please re-authenticate."
            ) from e
        else:
            _LOGGER.error("Unexpected error during client initialization.")
            return False

    coordinator = PhilipsPetsSeriesDataUpdateCoordinator(
        hass,
        client,
        delay_between_calls=0.5,
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Register services
    await async_setup_services(hass, client)
    
    # Register update listener for options changes
    entry.async_on_unload(
        entry.add_update_listener(async_reload_entry)
    )
    
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_services(hass: HomeAssistant, client: PetsSeriesClient):
    """Set up custom services for Philips Pets Series."""
    
    from homeassistant.helpers import config_validation as cv
    import voluptuous as vol
    from petsseries import HomeInviteRole

    async def handle_create_home(call):
        """Handle the create_home service."""
        name = call.data.get("name")
        if not name:
            _LOGGER.error("Service create_home: 'name' is required")
            return
        
        try:
            home = await client.homes_manager.create_home(name)
            _LOGGER.info("Created home: %s (%s)", home.name, home.id)
            # Trigger coordinator refresh to pick up new home
            for entry_id, entry_data in hass.data.get(DOMAIN, {}).items():
                coordinator = entry_data.get("coordinator")
                if coordinator:
                    await coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.exception("Failed to create home: %s", e)

    async def handle_send_home_invite(call):
        """Handle the send_home_invite service."""
        home_id = call.data.get("home_id")
        email = call.data.get("email")
        label = call.data.get("label")
        role_str = call.data.get("role", "MEMBER")
        
        if not all([home_id, email, label]):
            _LOGGER.error("Service send_home_invite: 'home_id', 'email', and 'label' are required")
            return
        
        try:
            role = HomeInviteRole(role_str)
        except (ValueError, TypeError) as e:
            _LOGGER.error("Invalid role '%s': %s", role_str, e)
            return
        
        # Find home object
        try:
            homes = await client.get_homes()
            home = next((h for h in homes if h.id == home_id), None)
            
            if not home:
                _LOGGER.error("Home with ID %s not found", home_id)
                return
            
            await client.homes_manager.send_invite(home, email, label, role)
            _LOGGER.info("Sent invite to %s for home %s", email, home.name)
            # Trigger coordinator refresh to pick up new invite
            for entry_id, entry_data in hass.data.get(DOMAIN, {}).items():
                coordinator = entry_data.get("coordinator")
                if coordinator:
                    await coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.exception("Failed to send invite: %s", e)

    async def handle_add_device(call):
        """Handle the add_device service."""
        home_id = call.data.get("home_id")
        product_ctn = call.data.get("product_ctn")
        
        if not all([home_id, product_ctn]):
            _LOGGER.error("Service add_device: 'home_id' and 'product_ctn' are required")
            return
        
        try:
            homes = await client.get_homes()
            home = next((h for h in homes if h.id == home_id), None)
            
            if not home:
                _LOGGER.error("Home with ID %s not found", home_id)
                return
            
            await client.devices_manager.add_device(home, product_ctn)
            _LOGGER.info("Added device %s to home %s", product_ctn, home.name)
            # Trigger coordinator refresh to pick up new device
            for entry_id, entry_data in hass.data.get(DOMAIN, {}).items():
                coordinator = entry_data.get("coordinator")
                if coordinator:
                    await coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.exception("Failed to add device: %s", e)

    async def handle_reset_device_filter(call):
        """Handle the reset_device_filter service."""
        # This one is tricky because we need the home and device object.
        # Targets are usually entity IDs.
        # We can iterate over the targets and map them to devices.
        # For simplicity, let's accept device_id and home_id as fields for now if not using targets,
        # but using targets is better.
        # Let's try to map from entity registry if possible, or iterate coordinator data.
        
        # NOTE: Simplified implementation expecting direct params or entity_id mapping
        # If calling from generic service, we might need to lookup device.
        # For now, let's just use home_id and device_id from fields to be safe.
        pass

    hass.services.async_register(DOMAIN, "create_home", handle_create_home)
    hass.services.async_register(DOMAIN, "send_home_invite", handle_send_home_invite)
    hass.services.async_register(DOMAIN, "add_device", handle_add_device)
    # hass.services.async_register(DOMAIN, "reset_device_filter", handle_reset_device_filter)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        client = hass.data[DOMAIN][entry.entry_id]["client"]
        await client.close()
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok

