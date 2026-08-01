"""Websocket API that tells the bundled cards which entity plays which role.

A card cannot guess entity IDs: users rename entities, and the slug of "Feed one
portion" is not stable across languages or renames.  Unique IDs are stable, but
the frontend never sees them.  This command does the lookup on the backend and
hands the card a role -> entity_id map, so the cards keep working after a rename.
"""

from __future__ import annotations

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import DOMAIN

# Unique-ID suffix -> the role the card asks for.  Suffixes are assigned in the
# platform modules and are load-bearing for entity history, so they change about
# as often as never.
#
# Only roles a card actually uses are listed.  Everything else stays reachable
# the normal way, through the device page; adding a role here that nothing reads
# is a promise to keep working that nobody is checking.
_ROLES = {
    # Feeding
    "feed_button": "feed_button",
    "number_feed_num": "feed_portions_now",
    "tuya_dp_202": "portion_size",
    "next_meal": "next_meal",
    "last_meal_dispensed_event": "last_meal_dispensed",
    # Conditions
    "food_level_low": "food_level_low",
    "food_outlet_stuck": "food_outlet_stuck",
    "filter_replacement_due": "filter_replacement_due",
    "tuya_dp_255": "feeding_fault",
    "reset_filter_button": "reset_filter",
    # Reachability
    "device_offline": "connectivity",
    "tuya_cloud_connected": "cloud_connected",
    # Camera
    "camera": "camera",
    "last_motion_snapshot": "last_motion_snapshot",
    "last_motion_detected_event": "last_motion",
    "switch_privacy_mode": "privacy_mode",
    "switch_motion_alarm": "motion_alarm",
    "switch_video_osd": "video_osd",
    "switch_pre_feed_snapshot": "pre_feed_snapshot",
    # Device
    "wifi_firmware_version": "firmware_wifi",
    "mcu_firmware_version": "firmware_mcu",
}


@callback
def async_register(hass: HomeAssistant) -> None:
    """Register the integration's websocket commands."""
    websocket_api.async_register_command(hass, ws_list_devices)


@callback
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/devices"})
def ws_list_devices(hass: HomeAssistant, connection, msg) -> None:
    """List Philips Pet Series devices and their role -> entity_id map."""
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    devices = []
    for device in device_registry.devices.values():
        philips_id = next(
            (domain_id for domain, domain_id in device.identifiers if domain == DOMAIN),
            None,
        )
        if philips_id is None:
            continue

        entities: dict[str, str] = {}
        for entry in er.async_entries_for_device(entity_registry, device.id):
            prefix = f"{philips_id}_"
            if entry.platform != DOMAIN or not entry.unique_id.startswith(prefix):
                continue
            role = _ROLES.get(entry.unique_id[len(prefix) :])
            if role is not None:
                entities[role] = entry.entity_id

        devices.append(
            {
                "device_id": device.id,
                "name": device.name_by_user or device.name,
                "model": device.model,
                "entities": entities,
            }
        )

    connection.send_result(msg["id"], {"devices": devices})
