"""Diagnostics support for Philips Pets Series integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

# Key names are matched exactly, so every credential has to be listed in full:
# "token" does not cover "id_token", which is a live bearer credential able to
# control the feeder and read the camera.
TO_REDACT = {
    "access_token",
    "refresh_token",
    "id_token",
    "code_verifier",
    "callback_url",
    "tuya_local_key",
    "client_id",
    "local_key",
    "token",
    "authorization",
}


def _frigate_example(cameras: list[dict]) -> list[str] | str:
    """Recording-only Frigate configuration for the discovered cameras."""
    if not cameras:
        return "No camera stream available; set Camera streaming to 'always'."
    lines = ["go2rtc:", "  streams:"]
    for index, camera in enumerate(cameras):
        name = "feeder" if index == 0 else f"feeder_{index + 1}"
        lines += [f"    {name}:", f'      - "{camera["stream_url"]}"']
    lines += ["", "cameras:"]
    for index, camera in enumerate(cameras):
        name = "feeder" if index == 0 else f"feeder_{index + 1}"
        lines += [
            f"  {name}:",
            "    ffmpeg:",
            "      input_args: preset-rtsp-restream -analyzeduration 1000000 -probesize 1000000",
            "      inputs:",
            f"        - path: rtsp://127.0.0.1:8554/{name}",
            "          roles:",
            "            - record",
            "    detect:",
            "      enabled: false",
            "    motion:",
            "      enabled: true",
            "    record:",
            "      enabled: true",
        ]
    return lines


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

    bridge = domain_data.get("bridge")
    if bridge is not None:
        # A ready-to-paste recorder configuration. The address is the hardest
        # part to discover, and the loopback form shown inside Home Assistant
        # does not work from a separate recorder.
        cameras = []
        for device in (coordinator.data.get("devices", []) if coordinator else []):
            endpoint = bridge.stream_endpoint(device)
            if endpoint and endpoint.get("url"):
                entry_info = {"name": device.name, "stream_url": endpoint["url"],
                              "address_source": endpoint.get("address_source")}
                if endpoint.get("note"):
                    entry_info["note"] = endpoint["note"]
                cameras.append(entry_info)
        data["camera_streaming"] = {
            "mode": bridge.camera_mode,
            "cameras": cameras,
            "frigate_example": _frigate_example(cameras),
            "documentation": "https://github.com/AboveColin/HA-Philips-Pet-Series/blob/main/docs/nvr.md",
        }

    if client:
        data["client"] = {
            "has_tuya_client": client.tuya_client is not None,
            "initialized": hasattr(client, "_initialized")
            and getattr(client, "_initialized", False),
        }

    return data
