from __future__ import annotations

import asyncio
import importlib
import ipaddress
import json
import datetime as dt
import logging
import os
import sys
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

# petsseries uses the generic ``tuya_mobile`` package for encrypted mobile API
# calls. It is vendored because that package is intentionally not published on
# PyPI yet; installing this integration must not require a manual package copy.
if "tuya_mobile" not in sys.modules:
    sys.modules["tuya_mobile"] = importlib.import_module(".tuya_mobile", __package__)

try:
    import petsseries
except ImportError as e:
    _LOGGER.error("Failed to import petsseries module: %s", e)
    raise

from petsseries.models import Event

from petsseries import PetsSeriesClient

from .const import (
    CONF_COUNTRY,
    CONF_HOME_IDS,
    CONF_ID_TOKEN,
    CONF_LANGUAGE,
    CONF_TIMEZONE,
    COUNTRY_DIAL_CODES,
    DOMAIN,
)
from .bridge import PhilipsCameraBridgeManager
from .datapoints import datapoints

PLATFORMS = [
    Platform.BINARY_SENSOR,
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
        home_ids: list[str] | None = None,
        tuya_device_id: str | None = None,
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
        self.home_ids = set(home_ids or [])
        self._tuya_device_id = tuya_device_id
        self._ota_store = Store(hass, 1, f"{DOMAIN}.ota_history")
        self.ota_history: dict[str, list[dict]] = {}

    def tuya_device_id(self, device) -> str:
        """Return the Tuya devId associated with a Philips device."""
        return getattr(device, "vendor_id", None) or self._tuya_device_id or device.id

    async def _load_ota_history(self) -> None:
        """Load previously observed OTA metadata once per coordinator."""
        if self.ota_history:
            return
        stored = await self._ota_store.async_load()
        if isinstance(stored, dict):
            self.ota_history = stored

    async def _save_ota_records(self, device_id: str, records: list[dict]) -> None:
        """Persist OTA records so signed URLs are captured when offered."""
        if not records:
            return
        self.ota_history[device_id] = records
        await self._ota_store.async_save(self.ota_history)

    async def _async_update_data(self):
        """Fetch data from API."""
        try:
            await self._load_ota_history()
            try:
                homes = await self._client.get_homes()
            except RuntimeError as err:
                # A config-entry reload can leave the old aiohttp session
                # closed while the coordinator task is still winding down.
                if "Session is closed" not in str(err):
                    raise
                self._client.session = None
                homes = await self._client.get_homes()
            if self.home_ids:
                homes = [home for home in homes if str(home.id) in self.home_ids]
            devices = []
            home_devices_by_home = {}
            meals = []
            events_by_home_and_type = {}
            invites_by_home = {}
            settings = {}
            full_settings = {}
            firmware_info = {}
            product_firmware_info = {}
            device_definitions = {}
            event_types = Event.get_event_types()
            tuya_status = None
            use_local_tuya = False
            if self._client.tuya_client:
                try:
                    configured_ip = getattr(self._client.tuya_client.device, "address", None)
                    use_local_tuya = bool(configured_ip and ipaddress.ip_address(configured_ip).is_private)
                except (ValueError, AttributeError):
                    use_local_tuya = False
            if use_local_tuya:
                try:
                    # This is account/device-global; fetching it once avoids one
                    # blocking LAN request per device on every coordinator cycle.
                    tuya_status = await asyncio.to_thread(self._client.get_tuya_status)
                except Exception as err:
                    _LOGGER.warning("Failed to fetch Tuya status: %s", err)
            now = dt_util.now()
            from_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            to_date = from_date + timedelta(days=1)

            for home in homes:
                try:
                    home_devices = await self._client.get_devices(home)
                    home_devices_by_home[home.id] = home_devices
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
                        settings[device.id] = device_settings or {}
                    except Exception as e:
                        _LOGGER.warning("Failed to fetch settings for device %s: %s", device.id, e)
                        settings[device.id] = {}

                    # Fetch full settings
                    try:
                        device_full_settings = await self._client.devices_manager.get_device_settings(home, device)
                        full_settings[device.id] = device_full_settings
                    except Exception as e:
                        _LOGGER.warning("Failed to fetch full settings for device %s: %s", device.id, e)

                    # Prefer the app-compatible cloud DP status. TinyTuya is
                    # only a fallback for installations with a real LAN IP.
                    if device.id in settings:
                        try:
                            cloud_device_id = self.tuya_device_id(device)
                            device_definitions[device.id] = await self._client.get_cloud_device_definition(
                                cloud_device_id
                            )
                            cloud_status = await self._client.get_cloud_device_status(
                                cloud_device_id
                            )
                            if isinstance(cloud_status.get("dps"), str):
                                cloud_status = {**cloud_status, **json.loads(cloud_status["dps"])}
                            elif isinstance(cloud_status.get("dps"), dict):
                                cloud_status = {**cloud_status, **cloud_status["dps"]}
                            for dp_id, dp_info in datapoints.items():
                                if str(dp_id) in cloud_status:
                                    cloud_status[dp_info["dpCode"]] = cloud_status[str(dp_id)]
                            # The current app uses DP 101 for PAW3300/3320
                            # quick feeding; older models use DP 201.
                            if device.product_ctn in {"PAW3300", "PAW3320"} and "101" in cloud_status:
                                cloud_status["feed_num"] = cloud_status["101"]
                            settings[device.id]["tuya_status"] = cloud_status
                        except Exception as err:
                            _LOGGER.debug("Cloud DP status unavailable for %s: %s", device.id, err)
                            # Never store None: a present-but-None tuya_status
                            # makes every entity's .get("tuya_status", {}).get()
                            # chain crash on add and drop the entity for the
                            # whole session. Fall back to an empty dict so
                            # entities load and simply report unavailable until
                            # the next successful cloud refresh.
                            settings[device.id]["tuya_status"] = tuya_status or {}

                    try:
                        firmware_info[device.id] = await self._client.get_cloud_firmware_info(
                            self.tuya_device_id(device)
                        )
                    except Exception as err:
                        _LOGGER.debug("Cloud OTA metadata unavailable for %s: %s", device.id, err)
                        firmware_info[device.id] = []
                    try:
                        product_firmware_info[device.id] = await self._client.get_product_firmware_info(
                            str(device.product_id or ""), device.id
                        )
                    except Exception as err:
                        _LOGGER.debug("Product OTA metadata unavailable for %s: %s", device.id, err)
                        product_firmware_info[device.id] = []
                    await self._save_ota_records(
                        device.id,
                        firmware_info[device.id] or product_firmware_info[device.id],
                    )

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
            base_data["tuya_status"] = tuya_status
            base_data["device_definitions"] = device_definitions

            # Fetch discovery config
            try:
                discovery_config = await self._client.discovery_manager.get_discovery_config()
                base_data["discovery_config"] = discovery_config
            except Exception as e:
                _LOGGER.warning("Failed to fetch discovery config: %s", e)
                base_data["discovery_config"] = None

            return {
                "homes": homes,
                "home_devices": home_devices_by_home,
                "devices": devices,
                "meals": meals,
                "invites": invites_by_home,
                "events_by_home_and_type": events_by_home_and_type,
                "event_types": event_types,
                "settings": settings,
                "full_settings": full_settings,
                "firmware_info": firmware_info,
                "device_definitions": device_definitions,
                "product_firmware_info": product_firmware_info,
                "ota_history": self.ota_history,
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

    # Regional metadata sent in the Tuya mobile requests: from the config entry
    # if the user chose it, else Home Assistant's own config, else neutral
    # defaults. Nothing region-specific is hardcoded in the package.
    os.environ["PETSERIES_TUYA_TIMEZONE"] = (
        data.get(CONF_TIMEZONE) or hass.config.time_zone or "UTC"
    )
    os.environ["PETSERIES_TUYA_LANG"] = (
        data.get(CONF_LANGUAGE) or hass.config.language or "en"
    ).split("-")[0]
    _country = (data.get(CONF_COUNTRY) or hass.config.country or "").upper()
    os.environ["PETSERIES_TUYA_COUNTRY_CODE"] = COUNTRY_DIAL_CODES.get(_country, "1")

    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    id_token = data.get(CONF_ID_TOKEN)

    async def save_tokens_callback(
        access_token: str, refresh_token: str, refreshed_id_token: str | None = None
    ) -> None:
        """Save tokens to config entry."""
        _LOGGER.debug("Saving new tokens to config entry")
        hass.config_entries.async_update_entry(
            entry,
            data={
                **entry.data,
                "access_token": access_token,
                "refresh_token": refresh_token,
                CONF_ID_TOKEN: refreshed_id_token or entry.data.get(CONF_ID_TOKEN),
            },
        )

    client = PetsSeriesClient(
        token_file=None,
        access_token=access_token,
        refresh_token=refresh_token,
        id_token=id_token,
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
        home_ids=data.get(CONF_HOME_IDS),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    bridge = PhilipsCameraBridgeManager(hass, entry, client, coordinator)
    try:
        await bridge.async_start()
    except Exception as err:
        await client.close()
        hass.data[DOMAIN].pop(entry.entry_id, None)
        raise ConfigEntryNotReady(
            f"Unable to start the built-in camera bridge: {err}"
        ) from err
    hass.data[DOMAIN][entry.entry_id]["bridge"] = bridge

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services
    await async_setup_services(hass, client)

    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove legacy manual camera options from pre-bundled-bridge entries."""
    if entry.version >= 4:
        return True
    obsolete = {
        "tuya_client_id",
        "tuya_ip",
        "tuya_local_key",
        "tuya_version",
        "stream_url",
    }
    data = {key: value for key, value in entry.data.items() if key not in obsolete}
    options = {key: value for key, value in entry.options.items() if key not in obsolete}
    hass.config_entries.async_update_entry(
        entry,
        data=data,
        options=options,
        version=4,
    )
    _LOGGER.info("Migrated Philips integration to automatic camera streaming")
    return True


async def async_setup_services(hass: HomeAssistant, client: PetsSeriesClient):
    """Set up custom services for Philips Pets Series."""
    if hass.data.get(DOMAIN, {}).get("services_registered"):
        return

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
    hass.data.setdefault(DOMAIN, {})["services_registered"] = True
    # hass.services.async_register(DOMAIN, "reset_device_filter", handle_reset_device_filter)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        entry_data = hass.data[DOMAIN][entry.entry_id]
        bridge = entry_data.get("bridge")
        if bridge is not None:
            await bridge.async_stop()
        client = entry_data["client"]
        await client.close()
        hass.data[DOMAIN].pop(entry.entry_id)
        if not any(key != "services_registered" for key in hass.data[DOMAIN]):
            hass.data[DOMAIN].pop("services_registered", None)

    return unload_ok
