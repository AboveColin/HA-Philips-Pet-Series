"""Diagnostics support for Philips Pets Series integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

TO_REDACT = {
    "access_token",
    "refresh_token",
    "tuya_local_key",
    "client_id",
    "local_key",
    "token",
    "authorization",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data: dict[str, Any] = {
        "entry": {
            "title": config_entry.title,
            "data": async_redact_data(config_entry.data, TO_REDACT),
            "options": async_redact_data(config_entry.options, TO_REDACT),
        },
    }

    if config_entry.entry_id not in hass.data.get(DOMAIN, {}):
        data["error"] = "Integration not initialized"
        return data

    domain_data = hass.data[DOMAIN][config_entry.entry_id]
    coordinator = domain_data.get("coordinator")
    client = domain_data.get("client")

    if coordinator:
        coordinator_info = {
            "last_update_success": coordinator.last_update_success,
            "update_interval": str(coordinator.update_interval),
        }
        # Check if last_update_time exists (it may not be available in all HA versions)
        if hasattr(coordinator, "last_update_time") and coordinator.last_update_time:
            coordinator_info["last_update"] = coordinator.last_update_time.isoformat()
        data["coordinator"] = coordinator_info

        if coordinator.data:
            # Include summary of coordinator data (redacted)
            coordinator_summary = {
                "homes_count": len(coordinator.data.get("homes", [])),
                "devices_count": len(coordinator.data.get("devices", [])),
                "meals_count": len(coordinator.data.get("meals", [])),
                "event_types_count": len(coordinator.data.get("event_types", [])),
                "settings_devices_count": len(coordinator.data.get("settings", {})),
            }
            data["coordinator"]["data_summary"] = coordinator_summary

    if client:
        data["client"] = {
            "has_tuya_client": client.tuya_client is not None,
            "initialized": hasattr(client, "_initialized")
            and getattr(client, "_initialized", False),
        }

    return data
