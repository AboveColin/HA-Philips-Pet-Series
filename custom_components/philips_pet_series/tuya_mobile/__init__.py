"""tuya-mobile: pure-Python Tuya *mobile* API signer + client.

A dependency-free reimplementation of Tuya's ``thing_security`` mobile-app
request signing, the encrypted mobile API client, and the MQTT signaling
credential derivation. Generic across Tuya-based apps — supply your app's Tuya
application credentials (extracted from its APK) and it works with no external
signer service, no qemu, and no native libraries.
"""
from .signer import (
    NativeSignerError,
    NativeTuyaSigner,
    PurePythonTuyaSigner,
    colon_hex,
)
from .client import TuyaMobileClient, canonical_string
from .mqtt_auth import mqtt_client_id, mqtt_credentials, mqtt_password, mqtt_username

__all__ = [
    "PurePythonTuyaSigner",
    "NativeTuyaSigner",
    "NativeSignerError",
    "colon_hex",
    "TuyaMobileClient",
    "canonical_string",
    "mqtt_credentials",
    "mqtt_client_id",
    "mqtt_username",
    "mqtt_password",
]

__version__ = "0.1.0"
