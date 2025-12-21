"""System health for Philips Pets Series integration."""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN


@callback
def async_register(
    hass: HomeAssistant, register: Any  # type: ignore[type-arg]
) -> None:
    """Register system health callbacks."""
    register.async_register_info(
        async_check_api_health,
    )


async def async_check_api_health(hass: HomeAssistant) -> dict[str, Any]:
    """Check the health of the Philips Pet Series API."""
    data: dict[str, Any] = {}

    # Check if we have any config entries
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        data["status"] = "not_configured"
        return data

    # Check each config entry
    healthy_entries = 0
    total_entries = len(entries)

    for entry in entries:
        if entry.entry_id not in hass.data.get(DOMAIN, {}):
            continue

        coordinator = hass.data[DOMAIN][entry.entry_id].get("coordinator")
        if coordinator and coordinator.last_update_success:
            healthy_entries += 1

    data["status"] = "ok" if healthy_entries == total_entries else "error"
    data["configured_entries"] = total_entries
    data["healthy_entries"] = healthy_entries

    if healthy_entries < total_entries:
        data["error"] = f"{total_entries - healthy_entries} of {total_entries} entries are not responding"

    return data

