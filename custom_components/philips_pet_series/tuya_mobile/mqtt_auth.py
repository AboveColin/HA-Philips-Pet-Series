"""Tuya mobile MQTT signaling credentials (pure Python).

Implements the Tuya Android SDK scheme (``com.thingclips.sdk.mqtt``):
the MQTT broker username/password are a straightforward MD5-hex derivation over
session fields — no native code involved (``MD5Util.md5AsBase64`` is misnamed;
it returns MD5 *hex*). Source references:

* password  (``dbqqppp.qddqppb``): ``md5hex(ecode)[8:24]``
* username  (``dbpdpbp.bdpdqbp``):
    ``partner_id + "_v1_" + app_id + "_" + chKey + "_mb_" + token +
      md5hex(md5hex(app_id) + ecode)[-16:]``

``chKey`` is the signer's ``channel_key()``; ``token`` is the session token
(the login ``uid`` in observed traffic); ``partner_id`` is the app's Tuya
partner prefix (e.g. ``p2065237`` for the Philips app).

NOTE: the MQTT ``client_id`` derivation (ends ``_DEFAULT``) is not yet confirmed
byte-for-byte and is validated during camera-bridge bring-up.
"""
from __future__ import annotations

import hashlib
import secrets
from typing import Optional


def _md5hex(value: str) -> str:
    return hashlib.md5(value.encode()).hexdigest()


def mqtt_password(global_material: str, ecode: str) -> str:
    """16-char MQTT password.

    Verified against a live device capture: the SDK's native command 2 computes
    ``md5(md5(G) + ecode)`` (32 hex) and takes its middle 16 chars, where ``G``
    is the signer's global key material (package_colonCert_appKey_appSecret).
    """
    return _md5hex(_md5hex(global_material) + ecode)[8:24]


def mqtt_username(app_id: str, ch_key: str, sid: str, ecode: str,
                  partner_id: str) -> str:
    """MQTT username for the ``smart/mb`` signaling channel.

    Verified against a live device capture: the ``_mb_`` body is the session
    ``sid`` followed by ``md5(md5(app_id) + ecode)[-16:]`` (the "token" the SDK
    concatenates is the sid, not the uid).
    """
    tail = _md5hex(_md5hex(app_id) + ecode)[-16:]
    return f"{partner_id}_v1_{app_id}_{ch_key}_mb_{sid}{tail}"


def mqtt_client_id(package: str, *, installation_id: Optional[str] = None,
                   tag: str = "DEFAULT") -> str:
    """Create a mobile MQTT client ID in the SDK's accepted shape.

    The opaque installation component is not an account credential. Generating
    a fresh one lets a local bridge coexist with the official app.
    """
    install = installation_id or secrets.token_hex(24)
    return f"{package}_mb_{install}_{tag}"


def mqtt_credentials(signer, *, uid: str, sid: str, ecode: str,
                     partner_id: str) -> dict:
    """Build the MQTT signaling credentials from a signer + session fields.

    ``signer`` supplies ``app_id`` and ``channel_key()``. The username embeds the
    session ``sid``; the topics use the ``uid``.
    """
    ch_key = signer.channel_key()
    return {
        "username": mqtt_username(signer.app_id, ch_key, sid, ecode, partner_id),
        "password": mqtt_password(signer.global_material(), ecode),
        # Subscribe/publish topics for the mobile signaling channel.
        "publish_topic": f"smart/mb/in/{uid}",
        "subscribe_topic": f"smart/mb/out/{uid}",
    }
