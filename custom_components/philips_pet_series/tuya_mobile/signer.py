"""Pure-Python reimplementation of Tuya's ``thing_security`` mobile signer.

Implements the Tuya mobile signing scheme:
computes three things, and all three are plain HMAC-SHA256 / SHA256 over ASCII
inputs — there is no whitebox cipher and no native dependency. This lets any
Tuya *mobile* app's API be called with no external signer, no qemu, and no
native blobs.

Everything hangs off one "global key material" string::

    G = package + "_" + colon_hex(cert) + "_" + app_key + "_" + app_secret

Primitives (ASCII in/out):

* ``channel_key()`` -> ``HMAC_SHA256(app_id, package + "_" + colon_hex(cert)).hex()[8:16]``
* ``derive_key(request_id, ecode)`` -> 16-byte AES key = ASCII of
  ``HMAC_SHA256(request_id, G [+ "_" + ecode]).hex()[:16]``
* ``sign(canonical)`` -> ``HMAC_SHA256(SHA256(G), canonical).hex()``

The signer is **parameterized by the app's Tuya application credentials**
(``app_id``, ``app_secret``, ``cert_sha256_hex``, ``app_key``, ``package``).
These are constant per app (extracted from that app's APK) and are the only
app-specific inputs — the algorithm itself is generic across Tuya apps.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import urllib.request
from pathlib import Path
from typing import Optional


class NativeSignerError(RuntimeError):
    """A configured external signer failed or returned invalid output."""


def colon_hex(cert_sha256_hex: str) -> str:
    """Render a cert SHA-256 as uppercase, colon-separated hex (Android style)."""
    h = cert_sha256_hex.replace(":", "").strip()
    return ":".join(h[i : i + 2] for i in range(0, len(h), 2)).upper()


class PurePythonTuyaSigner:
    """Drop-in ``thing_security`` signer implemented in pure Python."""

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        cert_sha256_hex: str,
        app_key: str,
        package: str,
    ) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.cert_sha256_hex = cert_sha256_hex
        self.app_key = app_key
        self.package = package

    # -- internal helpers ------------------------------------------------
    def cert_msg(self) -> str:
        return f"{self.package}_{colon_hex(self.cert_sha256_hex)}"

    def global_material(self) -> str:
        """The shared "global key material" string G."""
        return f"{self.cert_msg()}_{self.app_key}_{self.app_secret}"

    def _signing_key(self) -> bytes:
        return hashlib.sha256(self.global_material().encode()).digest()

    # -- public interface ------------------------------------------------
    def sign(self, canonical: str) -> str:
        """Sign a canonical request string -> lowercase hex HMAC-SHA256."""
        return hmac.new(
            self._signing_key(), canonical.encode(), hashlib.sha256
        ).hexdigest()

    def derive_key(self, request_id: str, ecode: Optional[str]) -> bytes:
        """Return the 16-byte per-request AES key."""
        g = self.global_material()
        message = g if not ecode else f"{g}_{ecode}"
        digest = hmac.new(
            request_id.encode(), message.encode(), hashlib.sha256
        ).hexdigest()
        return digest[:16].encode()

    def channel_key(self) -> str:
        """Return the account/app-global channel key (chKey)."""
        return hmac.new(
            self.app_id.encode(), self.cert_msg().encode(), hashlib.sha256
        ).hexdigest()[8:16]


class NativeTuyaSigner:
    """Legacy adapter that shells out to an external signer (executable or HTTP).

    Kept only as a fallback for environments that prefer to delegate signing to
    an out-of-process ``thing_security`` (e.g. a qemu-hosted native lib). The
    pure-Python signer above is preferred and needs none of this.

    The command must implement: ``sign`` (canonical on stdin -> hex),
    ``key <request_id> <ecode>`` (-> hex AES key), ``chkey`` (-> channel key).
    """

    def __init__(
        self,
        command: "str | os.PathLike[str]",
        *,
        app_id: str,
        app_secret: str,
        cert_sha256: str,
        key_global: Optional[str] = None,
        android_root: "Optional[str | os.PathLike[str]]" = None,
        service_token: str = "",
    ) -> None:
        raw = str(command)
        self.command = raw if raw.startswith(("http://", "https://")) else str(Path(raw).expanduser())
        self.android_root = str(android_root) if android_root else None
        self.service_token = service_token or os.environ.get("TUYA_SIGNER_SERVICE_TOKEN", "")
        self.environment = os.environ.copy()
        self.environment.update(
            TUYA_APP_ID=app_id, TUYA_APP_SECRET=app_secret, TUYA_CERT_SHA256_HEX=cert_sha256
        )
        if key_global:
            self.environment["TUYA_KEY_GLOBAL"] = key_global

    def _run(self, operation: str, *arguments: str, stdin: Optional[str] = None,
             extra_env: Optional[dict] = None) -> str:
        if self.command.startswith(("http://", "https://")):
            payload = {
                "operation": operation, "arguments": list(arguments),
                "stdin": stdin or "", "canonical": (extra_env or {}).get("TUYA_CANONICAL_STRING", ""),
            }
            req = urllib.request.Request(
                self.command, data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json",
                         "Authorization": f"Bearer {self.service_token}"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=25) as resp:
                    result = json.loads(resp.read())
            except Exception as exc:
                raise NativeSignerError(f"Signer service request failed: {exc}") from exc
            if not result.get("ok"):
                raise NativeSignerError(result.get("error", "Signer service failed"))
            value = str(result.get("value", "")).strip()
            if not value:
                raise NativeSignerError(f"Signer op {operation!r} returned no output")
            return value
        env = self.environment.copy()
        if extra_env:
            env.update(extra_env)
        if self.android_root:
            env["PETSERIES_TUYA_ANDROID_ROOT"] = self.android_root
        try:
            done = subprocess.run([self.command, operation, *arguments], input=stdin,
                                  text=True, capture_output=True, check=False, env=env, timeout=20)
        except OSError as exc:
            raise NativeSignerError(f"Unable to execute signer: {exc}") from exc
        if done.returncode:
            raise NativeSignerError(f"Signer op {operation!r} failed: {done.stderr.strip()[-400:]}")
        value = done.stdout.strip()
        if not value:
            raise NativeSignerError(f"Signer op {operation!r} returned no output")
        return value

    def sign(self, canonical: str) -> str:
        return self._run("sign", extra_env={"TUYA_CANONICAL_STRING": canonical})

    def derive_key(self, request_id: str, ecode: Optional[str]) -> bytes:
        value = self._run("key", request_id, ecode or "-")
        try:
            result = bytes.fromhex(value)
        except ValueError as exc:
            raise NativeSignerError("Signer returned an invalid key") from exc
        if len(result) not in (16, 24, 32):
            raise NativeSignerError("Signer returned an unexpected key length")
        return result

    def channel_key(self) -> str:
        return self._run("chkey")
