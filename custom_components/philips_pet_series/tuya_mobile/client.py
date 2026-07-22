"""Encrypted Tuya *mobile* API client (the flow used by Tuya Android apps).

Generic across Tuya apps: the request signing / session-key derivation is
delegated to a signer (see :mod:`tuya_mobile.signer`), and the app identity
(``app_id``) comes from that signer or is passed explicitly. Nothing here is
vendor-specific.
"""
from __future__ import annotations

import asyncio
import base64
import gzip
import hashlib
import json
import logging
import os
import time
import uuid
from typing import Any, Dict, Iterable, List, Optional

import aiohttp
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_LOGGER = logging.getLogger(__name__)

SIGN_KEYS = {
    "a", "appVersion", "chKey", "clientId", "deviceId", "et", "h5",
    "h5Token", "lang", "lat", "lon", "n4h5", "os", "postData", "requestId",
    "sid", "sp", "time", "ttid", "v",
}


def _swap_md5(value: str) -> str:
    digest = hashlib.md5(value.encode()).hexdigest()
    return digest[8:16] + digest[0:8] + digest[24:32] + digest[16:24]


def canonical_string(params: Dict[str, str]) -> str:
    parts = []
    for key in sorted(params):
        value = params[key]
        if key in SIGN_KEYS and value:
            if key == "postData":
                value = _swap_md5(value)
            parts.append(f"{key}={value}")
    return "||".join(parts)


def _encrypt(key: bytes, payload: Dict[str, Any]) -> str:
    nonce = os.urandom(12)
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
    return base64.b64encode(nonce + AESGCM(key).encrypt(nonce, body, None)).decode()


def _decrypt(key: bytes, value: str) -> Dict[str, Any]:
    raw = base64.b64decode(value)
    plain = AESGCM(key).decrypt(raw[:12], raw[12:], None)
    try:
        plain = gzip.decompress(plain)
    except OSError:
        pass
    return json.loads(plain.decode())


def _walk(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


class TuyaMobileClient:
    """Call the encrypted Tuya mobile endpoints used by Tuya Android apps."""

    BASE_URL = "https://a1.tuyaeu.com/api.json"
    APP_VERSION = "2.2.1"

    def __init__(
        self,
        signer,
        session: aiohttp.ClientSession,
        *,
        app_id: Optional[str] = None,
        device_id: str = "",
    ) -> None:
        self.signer = signer
        self.session = session
        # App identity comes from the signer (which holds the app credentials)
        # unless overridden explicitly.
        self.app_id = app_id or getattr(signer, "app_id", "") or ""
        self.sid: Optional[str] = None
        self.ecode: Optional[str] = None
        self.uid: Optional[str] = None
        self.mobile_url = self.BASE_URL
        # Tuya validates a stable installation ID; supply the captured value.
        self.device_id = device_id or os.environ.get("PETSERIES_TUYA_DEVICE_ID", "")

    async def _call(self, action: str, payload: Dict[str, Any], *, version: str = "1.0") -> Dict[str, Any]:
        request_id = str(uuid.uuid4())
        key = await asyncio.to_thread(self.signer.derive_key, request_id, self.ecode)
        encrypted = _encrypt(key, payload)
        params: Dict[str, str] = {
            "a": action,
            "v": version,
            "clientId": self.app_id,
            "os": "Android",
            "appVersion": self.APP_VERSION,
            "channel": "sdk",
            "osSystem": "14",
            "sdkVersion": "6.7.0",
            "deviceCoreVersion": "6.7.0",
            "platform": "Pixel 7",
            "timeZoneId": os.environ.get("PETSERIES_TUYA_TIMEZONE") or "UTC",
            "cp": "gzip",
            "nd": "1",
            "bizDM": "ipc",
            "lang": os.environ.get("PETSERIES_TUYA_LANG") or "en",
            "ttid": "android",
            "et": "3",
            "chKey": await asyncio.to_thread(self.signer.channel_key),
            "deviceId": self.device_id or self.uid or "",
            "time": str(int(time.time())),
            "requestId": request_id,
            "postData": encrypted,
        }
        if self.sid:
            params["sid"] = self.sid
        params["sign"] = await asyncio.to_thread(self.signer.sign, canonical_string(params))
        async with self.session.post(self.mobile_url, data=params) as response:
            envelope = await response.json(content_type=None)
        if "result" not in envelope:
            error_code = envelope.get("errorCode") or envelope.get("code") or "unknown"
            error_msg = envelope.get("errorMsg") or envelope.get("msg") or "no result"
            raise RuntimeError(f"Tuya mobile API request {action} failed: {error_code} {error_msg}")
        return _decrypt(key, envelope["result"])

    async def login_with_jwt(self, id_token: str, country_code: str = "",
                             platform: str = "PhilipsDA") -> Dict[str, Any]:
        """Third-party (JWT) login. ``platform`` is the app's third-party tag."""
        result = await self._call(
            "thing.m.user.third.login",
            {
                "countryCode": country_code or os.environ.get("PETSERIES_TUYA_COUNTRY_CODE") or "1",
                "accessToken": id_token,
                "type": "jwt",
                "extraInfo": json.dumps({"platform": platform}),
                "options": '{"group": 1}',
            },
        )
        data: Dict[str, Any] = result
        while isinstance(data.get("result"), dict):
            data = data["result"]
        self.sid = data.get("sid") or data.get("session") or data.get("sessionId")
        self.ecode = data.get("ecode") or data.get("eCode") or data.get("encryptCode")
        self.uid = data.get("uid") or data.get("userId")
        if data.get("success") is False or data.get("errorCode") or data.get("errorMsg"):
            raise RuntimeError(
                "Tuya third-party login failed: "
                f"{data.get('errorCode') or 'unknown'} {data.get('errorMsg') or ''}".strip()
            )
        if not isinstance(self.ecode, str) or not self.ecode:
            raise RuntimeError("Tuya third-party login returned no encryption code")
        mobile_url = data.get("domain", {}).get("mobileApiUrl") or data.get("mobileApiUrl")
        if mobile_url:
            self.mobile_url = mobile_url.rstrip("/") + "/api.json"
        if not self.sid:
            raise RuntimeError("Tuya third-party login returned no session")
        return data

    # Back-compat alias (petsseries historically called this name).
    login_with_philips_token = login_with_jwt

    async def get_local_keys(self, device_ids: List[str]) -> List[Dict[str, Any]]:
        homes = await self._call("m.life.home.space.list", {})
        wanted = set(device_ids)
        records = []
        gids = {
            obj.get("gid") or obj.get("groupId") or obj.get("homeId")
            for obj in _walk(homes)
            if obj.get("gid") or obj.get("groupId") or obj.get("homeId")
        }
        for gid in gids:
            response = await self._call("m.life.my.group.device.list", {"gid": gid}, version="2.2")
            for obj in _walk(response):
                local_key = obj.get("localKey") or obj.get("local_key")
                device_id = obj.get("devId") or obj.get("deviceId") or obj.get("id")
                if local_key and (not wanted or str(device_id) in wanted):
                    records.append({
                        "device_id": device_id, "local_key": local_key,
                        "ip": obj.get("ip") or obj.get("lanIp"), "name": obj.get("name"),
                        "uuid": obj.get("uuid"),
                        "is_online": obj.get("isOnline", obj.get("cloudOnline")),
                    })
        unique = {(str(i.get("device_id")), str(i.get("local_key"))): i for i in records}
        return list(unique.values())

    async def get_device_status(self, device_id: str, gateway_id: str = "") -> Dict[str, Any]:
        result = await self._call("s.m.dev.dp.get", {"devId": device_id, "gwId": gateway_id})
        if result.get("success") is False or result.get("errorCode") or result.get("errorMsg"):
            raise RuntimeError(
                "Tuya status request failed: "
                f"{result.get('errorCode') or 'unknown'} {result.get('errorMsg') or ''}".strip()
            )
        return result

    async def publish_dps(self, device_id: str, dps: Dict[str, Any], gateway_id: str = "") -> Dict[str, Any]:
        result = await self._call(
            "thing.m.device.dp.publish",
            {"devId": device_id, "gwId": gateway_id, "dps": json.dumps(dps, separators=(",", ":"))},
        )
        if result.get("success") is False or result.get("errorCode") or result.get("errorMsg"):
            raise RuntimeError(
                "Tuya DP publish failed: "
                f"{result.get('errorCode') or 'unknown'} {result.get('errorMsg') or ''}".strip()
            )
        return result
