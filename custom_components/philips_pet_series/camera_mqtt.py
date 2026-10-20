"""MQTT signaling settings for the camera bridge.

A feeder set up in the Philips Pet Series app and one set up in the Philips
HomeID app live in different Tuya apps. The bridge signs in to MQTT as the app
that holds the camera, so the partner id in the username, the app id and key in
the credentials, and the package in the client id all come from that app's Tuya
session.

This module imports nothing from Home Assistant, so the tests run under plain
pytest.
"""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlsplit

from tuya_mobile import mqtt_client_id, mqtt_credentials

# Tuya's mobile API and MQTT brokers are region-specific and share a host
# suffix ("a1.tuyaeu.com" -> "m1.tuyaeu.com").
_DEFAULT_MQTT_HOST = "m1.tuyaeu.com"
_MQTT_PORT = 8883


async def mqtt_settings(tuya: Any, device_id: str) -> dict[str, Any]:
    """MQTT settings for one camera, from its own app's Tuya session.

    ``tuya`` is a ``petsseries.tuya_app.TuyaSession``: the logged-in client, the
    backend (Philips app) it belongs to, and the partner id from its login.
    """
    mobile = tuya.client
    if mobile is None or not mobile.uid or not mobile.sid or not mobile.ecode:
        raise RuntimeError("Tuya mobile session has no MQTT fields")
    mqtt = await asyncio.to_thread(
        mqtt_credentials,
        mobile.signer,
        uid=mobile.uid,
        sid=mobile.sid,
        ecode=mobile.ecode,
        partner_id=tuya.partner_id,
    )
    mqtt["publish_topic"] = f"smart/mb/out/{device_id}"
    mqtt["subscribe_topic"] = f"smart/mb/in/{device_id}"
    return {
        **mqtt,
        "broker": mqtt_broker(mobile),
        "client_id": mqtt_client_id(tuya.backend.package),
        "uid": mobile.uid,
    }


def mqtt_broker(mobile: Any) -> str:
    """Derive the regional MQTT broker from the session's API endpoint.

    Tuya assigns each account to a regional data centre and the mobile API
    host tracks it ("a1.tuyaeu.com", "a1.tuyaus.com", ...).  The signing
    client rewrites its endpoint from the login response, so the MQTT broker
    has to follow it -- pinning the EU broker breaks every other region.
    """
    host = ""
    try:
        host = urlsplit(getattr(mobile, "mobile_url", "") or "").hostname or ""
    except ValueError:
        host = ""
    labels = host.split(".")
    if len(labels) >= 2 and labels[-1] and labels[-2]:
        # Swap only the leading service label ("a1" -> "m1"), keeping the
        # regional domain intact.
        broker_host = ".".join(["m1", *labels[1:]])
    else:
        broker_host = _DEFAULT_MQTT_HOST
    return f"ssl://{broker_host}:{_MQTT_PORT}"
