"""Self-contained pure-Go camera bridge supervision.

The bridge process runs inside Home Assistant and asks this module for fresh
Tuya WebRTC/MQTT material over a token-protected loopback endpoint. No camera
credentials, RTSP URL, sidecar, qemu process, or manual options are required.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
import hashlib
import logging
import os
from pathlib import Path
import platform
import secrets
import sys
import time
from typing import Any
from urllib.parse import urlsplit

from aiohttp import web
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from tuya_mobile import mqtt_client_id, mqtt_credentials

from .const import CONF_CAMERA_MODE

_LOGGER = logging.getLogger(__name__)

BRIDGE_PORT_BASE = 8560
BRIDGE_PACKAGE = "com.versuni.nbx.petsseries"
BRIDGE_PARTNER_ID = "p2065237"
CAMERA_PRODUCT_PREFIXES = ("PAW53",)

# Feeders allow only a small number of simultaneous P2P live sessions, and
# opening one can evict a session already held by the Philips app.  "on_demand"
# therefore mirrors the app: hold a session only while something is watching.
# "always" keeps the RTSP endpoint up permanently, which external consumers
# (an NVR pulling the stream directly) need; "disabled" never opens a session.
CAMERA_MODE_ON_DEMAND = "on_demand"
CAMERA_MODE_ALWAYS = "always"
CAMERA_MODE_DISABLED = "disabled"
CAMERA_MODES = (CAMERA_MODE_ON_DEMAND, CAMERA_MODE_ALWAYS, CAMERA_MODE_DISABLED)

# How long an on-demand bridge stays up after the last stream request.  HA's
# stream component re-requests the source periodically while a viewer is
# attached, so this only has to outlast the gap between those requests.
IDLE_TIMEOUT = timedelta(minutes=5)
_IDLE_CHECK_INTERVAL = 30

# A healthy bridge logs media progress continuously.  If it goes quiet while
# the process is still alive it has lost its P2P session without exiting, which
# the exit-driven monitor below would never notice.
_STALL_TIMEOUT = 120.0
_HEALTHY_LOG_MARKER = "camera_recv"

# Restart backoff: retrying every few seconds re-mints a cloud session against
# a device that is already struggling, so back off and eventually give up.
_RESTART_BACKOFF_START = 5
_RESTART_BACKOFF_MAX = 300
_RESTART_MAX_ATTEMPTS = 8

# Tuya's mobile API and MQTT brokers are region-specific and share a host
# suffix ("a1.tuyaeu.com" -> "m1.tuyaeu.com").
_DEFAULT_MQTT_HOST = "m1.tuyaeu.com"
_MQTT_PORT = 8883


# The camera bridge binary is cross-compiled in CI and published as release
# assets on the tuya-ipc-terminal repo, then downloaded + SHA-256-verified on
# demand (no binaries shipped in this repo). A matching binary dropped into
# ./bin/ overrides the download (development / offline installs).
BRIDGE_BINARY_REPO = "AboveColin/tuya-ipc-terminal"
BRIDGE_BINARY_TAG = "v1.0.0"
_BRIDGE_ARCH_MAP = {
    "x86_64": "amd64",
    "amd64": "amd64",
    "aarch64": "arm64",
    "arm64": "arm64",
    "armv7l": "arm",
    "armv6l": "arm",
    "arm": "arm",
}


@dataclass(slots=True)
class BridgeProcess:
    """One RTSP process and its stable device mapping."""

    device_id: str
    device_key: str
    port: int
    path: str
    process: asyncio.subprocess.Process
    log_task: asyncio.Task[None]
    monitor_task: asyncio.Task[None] | None = None
    # Wall-clock of the last stream request and the last sign of media
    # progress, used to reap idle sessions and detect stalled ones.
    last_requested: float = field(default_factory=time.monotonic)
    last_healthy: float = field(default_factory=time.monotonic)

    @property
    def stream_url(self) -> str:
        """Return the RTSP URL visible inside Home Assistant."""
        return f"rtsp://127.0.0.1:{self.port}{self.path}"


class PhilipsCameraBridgeManager:
    """Serve credentials and supervise pure-Go RTSP bridge processes."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: Any,
        coordinator: Any,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.client = client
        self.coordinator = coordinator
        self._token = secrets.token_urlsafe(32)
        self._runner: web.AppRunner | None = None
        self._sidecar_port: int | None = None
        self._processes: dict[str, BridgeProcess] = {}
        self._device_ids: set[str] = set()
        self._credential_lock = asyncio.Lock()
        self._stopping = False
        self._cameras: dict[str, Any] = {}
        self._ports: dict[str, int] = {}
        self._start_lock = asyncio.Lock()
        self._idle_task: asyncio.Task[None] | None = None

    @property
    def camera_mode(self) -> str:
        """Return the configured camera streaming mode."""
        mode = {**self.entry.data, **self.entry.options}.get(
            CONF_CAMERA_MODE, CAMERA_MODE_ON_DEMAND
        )
        return mode if mode in CAMERA_MODES else CAMERA_MODE_ON_DEMAND

    @property
    def processes(self) -> dict[str, BridgeProcess]:
        """Expose a read-only snapshot for diagnostics and camera entities."""
        return dict(self._processes)

    async def async_start(self) -> None:
        """Start the private credential endpoint and, if configured, bridges.

        In ``on_demand`` mode no P2P session is opened here: the feeder only
        tolerates a small number of concurrent sessions and opening one can
        evict the Philips app, so a session is minted when a stream is actually
        requested and released once nothing is watching.
        """
        devices = [
            device
            for device in self.coordinator.data.get("devices", [])
            if self._is_camera(device)
        ]
        if not devices:
            _LOGGER.info("No Philips camera-capable devices found")
            return

        mode = self.camera_mode
        if mode == CAMERA_MODE_DISABLED:
            _LOGGER.info("Camera streaming disabled; no camera bridge started")
            return

        # Reserve a stable port per device so a bridge started later keeps the
        # RTSP URL it was first given.
        for index, device in enumerate(devices):
            self._cameras[str(device.id)] = device
            self._ports[str(device.id)] = BRIDGE_PORT_BASE + index

        await self._async_start_credential_server()
        try:
            if mode == CAMERA_MODE_ALWAYS:
                for device in devices:
                    await self._async_start_device(device, self._ports[str(device.id)])
            else:
                self._idle_task = self.hass.async_create_background_task(
                    self._async_reap_idle(), name=f"{DOMAIN_LOG_PREFIX}-idle-reaper"
                )
        except Exception:
            await self.async_stop()
            raise

    async def async_get_stream_url(self, device: Any) -> str | None:
        """Return an RTSP URL, minting an on-demand session when required."""
        if self._stopping or self.camera_mode == CAMERA_MODE_DISABLED:
            return None
        device_key = str(device.id)
        async with self._start_lock:
            bridge = self._processes.get(device_key)
            if bridge is not None and bridge.process.returncode is None:
                bridge.last_requested = time.monotonic()
                return bridge.stream_url
            if self.camera_mode == CAMERA_MODE_ALWAYS:
                # Supervision owns the lifecycle in this mode, so a missing
                # bridge means it is mid-restart rather than idle.
                return None
            if self._sidecar_port is None:
                await self._async_start_credential_server()
            self._cameras.setdefault(device_key, device)
            port = self._ports.setdefault(
                device_key, BRIDGE_PORT_BASE + len(self._ports)
            )
            try:
                await self._async_start_device(device, port)
            except Exception as err:
                _LOGGER.error("Unable to start camera bridge on demand: %s", err)
                return None
            bridge = self._processes.get(device_key)
            return bridge.stream_url if bridge is not None else None

    async def _async_reap_idle(self) -> None:
        """Release on-demand sessions once nothing has asked for the stream."""
        idle_seconds = IDLE_TIMEOUT.total_seconds()
        while not self._stopping:
            await asyncio.sleep(_IDLE_CHECK_INTERVAL)
            now = time.monotonic()
            for device_key, bridge in list(self._processes.items()):
                if now - bridge.last_requested < idle_seconds:
                    continue
                _LOGGER.debug("Releasing idle camera session for %s", device_key)
                await self._async_stop_bridge(device_key)

    async def _async_stop_bridge(self, device_key: str) -> None:
        """Terminate one bridge and release its P2P session."""
        bridge = self._processes.pop(device_key, None)
        if bridge is None:
            return
        if bridge.monitor_task is not None:
            bridge.monitor_task.cancel()
        await self._async_stop_bridge_process(bridge)

    async def async_stop(self) -> None:
        """Stop all child processes and remove the credential endpoint."""
        self._stopping = True
        if self._idle_task is not None:
            self._idle_task.cancel()
            try:
                await self._idle_task
            except asyncio.CancelledError:
                pass
            self._idle_task = None
        processes = list(self._processes.values())
        self._processes.clear()
        for bridge in processes:
            if bridge.monitor_task is not None:
                bridge.monitor_task.cancel()
            bridge.log_task.cancel()
            if bridge.process.returncode is None:
                bridge.process.terminate()
        for bridge in processes:
            if bridge.monitor_task is not None:
                try:
                    await bridge.monitor_task
                except asyncio.CancelledError:
                    pass
            if bridge.process.returncode is None:
                try:
                    await asyncio.wait_for(bridge.process.wait(), timeout=8)
                except TimeoutError:
                    bridge.process.kill()
                    await bridge.process.wait()
            try:
                await bridge.log_task
            except asyncio.CancelledError:
                pass

        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
            self._sidecar_port = None

    def stream_url(self, device: Any) -> str | None:
        """Return the automatic stream URL for a Philips device."""
        bridge = self._processes.get(str(getattr(device, "id", "")))
        return bridge.stream_url if bridge is not None else None

    @staticmethod
    def _is_camera(device: Any) -> bool:
        """Identify products whose Philips hardware includes the IPC camera."""
        product = str(getattr(device, "product_ctn", "") or "").upper()
        return product.startswith(CAMERA_PRODUCT_PREFIXES)

    async def _async_start_credential_server(self) -> None:
        app = web.Application()
        app.router.add_get("/webrtc", self._handle_webrtc)
        app.router.add_get("/health", self._handle_health)
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await site.start()
        server = site._server  # aiohttp exposes the selected ephemeral port here.
        if server is None or not server.sockets:
            raise RuntimeError("credential endpoint did not bind a socket")
        self._sidecar_port = int(server.sockets[0].getsockname()[1])

    async def _handle_health(self, request: web.Request) -> web.Response:
        if not self._authorized(request):
            raise web.HTTPUnauthorized()
        return web.json_response({"ok": True})

    async def _handle_webrtc(self, request: web.Request) -> web.Response:
        if not self._authorized(request):
            raise web.HTTPUnauthorized()
        device_id = request.query.get("devId", "")
        if not device_id or device_id not in self._device_ids:
            raise web.HTTPNotFound()

        try:
            async with self._credential_lock:
                await self.client.ensure_token_valid()
                webrtc = await self.client.get_cloud_webrtc_config(device_id)
                if not webrtc:
                    raise RuntimeError("Tuya returned an empty WebRTC configuration")
                definition = await self.client.get_cloud_device_definition(device_id)
                local_key = definition.get("localKey") if isinstance(definition, dict) else None
                if local_key:
                    webrtc["localKey"] = local_key

                mobile = self.client._tuya_mobile
                if mobile is None or not mobile.uid or not mobile.sid or not mobile.ecode:
                    raise RuntimeError("Tuya mobile session has no MQTT fields")
                mqtt = await asyncio.to_thread(
                    mqtt_credentials,
                    mobile.signer,
                    uid=mobile.uid,
                    sid=mobile.sid,
                    ecode=mobile.ecode,
                    partner_id=BRIDGE_PARTNER_ID,
                )
                mqtt["publish_topic"] = f"smart/mb/out/{device_id}"
                mqtt["subscribe_topic"] = f"smart/mb/in/{device_id}"
                webrtc["mqtt"] = {
                    **mqtt,
                    "broker": self._mqtt_broker(mobile),
                    "client_id": mqtt_client_id(BRIDGE_PACKAGE),
                    "uid": mobile.uid,
                }
            return web.json_response(webrtc)
        except Exception as err:
            _LOGGER.error("Unable to prepare camera bridge credentials: %s", err)
            return web.json_response({"error": "credential refresh failed"}, status=502)

    @staticmethod
    def _mqtt_broker(mobile: Any) -> str:
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

    def _authorized(self, request: web.Request) -> bool:
        expected = f"Bearer {self._token}"
        return secrets.compare_digest(request.headers.get("Authorization", ""), expected)

    async def _async_start_device(self, device: Any, port: int) -> None:
        if self._sidecar_port is None:
            raise RuntimeError("credential endpoint is not running")
        device_id = str(
            getattr(device, "vendor_id", None)
            or self.coordinator.tuya_device_id(device)
        )
        if not device_id:
            raise RuntimeError("camera device has no Tuya device ID")
        device_key = str(device.id)
        self._device_ids.add(device_id)
        path = f"/philips-pet-{device_key.lower()}"
        binary = await self._ensure_binary()
        workdir = Path(self.hass.config.path(".philips_pet_series", "bridge", device_key))
        await asyncio.to_thread(workdir.mkdir, parents=True, exist_ok=True)

        env = os.environ.copy()
        env.update(
            PETSERIES_DEVICE_ID=device_id,
            PETSERIES_DEVICE_NAME=str(getattr(device, "name", "Philips Pet Series Camera")),
            PETSERIES_PRODUCT_ID=str(getattr(device, "product_id", "") or ""),
            PETSERIES_DEVICE_UUID=device_key,
            PETSERIES_DEVICE_SKILL='{"p2pType":4}',
            PETSERIES_RTSP_PATH=path,
            PETSERIES_CREDS_SIDECAR=f"http://127.0.0.1:{self._sidecar_port}",
            PETSERIES_SIDECAR_TOKEN=self._token,
            PETSERIES_REQUIRE_SIDECAR="1",
        )
        process = await asyncio.create_subprocess_exec(
            str(binary),
            "rtsp",
            "start",
            "--port",
            str(port),
            cwd=workdir,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        log_task = asyncio.create_task(
            self._async_read_logs(device_key, process),
            name=f"{DOMAIN_LOG_PREFIX}-{device_key}",
        )
        bridge = BridgeProcess(device_id, device_key, port, path, process, log_task)
        try:
            await self._async_wait_until_ready(bridge)
        except Exception:
            log_task.cancel()
            if process.returncode is None:
                process.terminate()
                await process.wait()
            raise
        self._processes[device_key] = bridge
        bridge.monitor_task = asyncio.create_task(
            self._async_monitor(device, bridge),
            name=f"{DOMAIN_LOG_PREFIX}-monitor-{device_key}",
        )
        _LOGGER.info("Pure-Go camera bridge ready for %s on port %d", device_key, port)

    async def _async_monitor(self, device: Any, bridge: BridgeProcess) -> None:
        """Supervise a bridge: restart it when it exits, or when it stalls.

        A bridge that loses its P2P session does not necessarily exit, so
        waiting on the process alone can leave a permanently silent stream.
        Watch for both conditions and restart with a backoff, since retrying
        tightly re-mints cloud sessions against a device that is already
        struggling.
        """
        reason = await self._async_wait_for_failure(bridge)
        if self._stopping:
            return
        if self._processes.get(bridge.device_key) is bridge:
            self._processes.pop(bridge.device_key, None)
            await self._async_stop_bridge_process(bridge)
        # An idle on-demand session that was reaped needs no replacement; it is
        # re-created on the next stream request.
        if self.camera_mode == CAMERA_MODE_ON_DEMAND and (
            time.monotonic() - bridge.last_requested >= IDLE_TIMEOUT.total_seconds()
        ):
            _LOGGER.debug(
                "Camera bridge for %s stopped while idle (%s); not restarting",
                bridge.device_key,
                reason,
            )
            return
        _LOGGER.error("Camera bridge for %s %s; restarting", bridge.device_key, reason)

        delay = _RESTART_BACKOFF_START
        for attempt in range(1, _RESTART_MAX_ATTEMPTS + 1):
            await asyncio.sleep(delay)
            if self._stopping:
                return
            try:
                await self._async_start_device(device, bridge.port)
                return
            except Exception as err:
                _LOGGER.error(
                    "Unable to restart camera bridge for %s (attempt %s/%s): %s",
                    bridge.device_key,
                    attempt,
                    _RESTART_MAX_ATTEMPTS,
                    err,
                )
                delay = min(delay * 2, _RESTART_BACKOFF_MAX)
        _LOGGER.error(
            "Giving up on the camera bridge for %s after %s attempts; reload the "
            "integration to try again",
            bridge.device_key,
            _RESTART_MAX_ATTEMPTS,
        )

    async def _async_wait_for_failure(self, bridge: BridgeProcess) -> str:
        """Block until the bridge exits or stops making media progress."""
        waiter = asyncio.ensure_future(bridge.process.wait())
        try:
            while True:
                done, _ = await asyncio.wait({waiter}, timeout=_STALL_TIMEOUT / 4)
                if waiter in done:
                    return f"exited with status {waiter.result()}"
                if self._stopping:
                    return "stopped"
                if time.monotonic() - bridge.last_healthy > _STALL_TIMEOUT:
                    return (
                        f"stopped delivering media for {_STALL_TIMEOUT:.0f}s "
                        "(P2P session lost)"
                    )
        finally:
            if not waiter.done():
                waiter.cancel()

    @staticmethod
    async def _async_stop_bridge_process(bridge: BridgeProcess) -> None:
        """Terminate a bridge process and stop tailing its logs."""
        bridge.log_task.cancel()
        if bridge.process.returncode is None:
            bridge.process.terminate()
            try:
                await asyncio.wait_for(bridge.process.wait(), timeout=10)
            except asyncio.TimeoutError:
                bridge.process.kill()
                await bridge.process.wait()

    async def _async_wait_until_ready(self, bridge: BridgeProcess) -> None:
        for _ in range(100):
            if bridge.process.returncode is not None:
                raise RuntimeError(
                    f"camera bridge exited with status {bridge.process.returncode}"
                )
            try:
                _reader, writer = await asyncio.open_connection("127.0.0.1", bridge.port)
            except OSError:
                await asyncio.sleep(0.1)
                continue
            writer.close()
            await writer.wait_closed()
            return
        raise TimeoutError("camera bridge did not open its RTSP port")

    async def _async_read_logs(
        self, device_key: str, process: asyncio.subprocess.Process
    ) -> None:
        if process.stdout is None:
            return
        try:
            async for raw_line in process.stdout:
                line = raw_line.decode(errors="replace").rstrip()
                # Media progress is the liveness signal the stall watchdog uses;
                # record it before the log-level filtering below.
                if _HEALTHY_LOG_MARKER in line and "_len=" in line:
                    bridge = self._processes.get(device_key)
                    if bridge is not None:
                        bridge.last_healthy = time.monotonic()
                if (
                    "failed to read request line: EOF" in line
                    or "use of closed network connection" in line
                ):
                    _LOGGER.debug("Camera bridge %s: %s", device_key, line)
                    continue
                if " ERR " in line or " WRN " in line:
                    _LOGGER.warning("Camera bridge %s: %s", device_key, line)
                else:
                    _LOGGER.debug("Camera bridge %s: %s", device_key, line)
        except asyncio.CancelledError:
            raise

    @staticmethod
    def _platform_tags() -> tuple[str, str, str]:
        """Return (os, arch, ext) for the current host."""
        machine = platform.machine().lower()
        arch = _BRIDGE_ARCH_MAP.get(machine)
        if arch is None:
            raise RuntimeError(f"unsupported camera bridge architecture: {machine}")
        if sys.platform.startswith("linux"):
            osname = "linux"
        elif sys.platform == "darwin":
            osname = "darwin"
        elif sys.platform.startswith("win"):
            osname = "windows"
        else:
            raise RuntimeError(f"unsupported OS for camera bridge: {sys.platform}")
        return osname, arch, ".exe" if osname == "windows" else ""

    @staticmethod
    def _make_executable(path: Path) -> None:
        if not os.access(path, os.X_OK):
            path.chmod(path.stat().st_mode | 0o111)

    async def _ensure_binary(self) -> Path:
        """Resolve the camera bridge binary, downloading it on first use.

        Order: a binary committed/dropped into ./bin/ wins (dev / offline); then a
        previously downloaded+cached copy; otherwise download the matching release
        asset and verify its SHA-256 against the release checksums file.
        """
        osname, arch, ext = self._platform_tags()
        # 1) local override in the integration's bin/ (new or legacy name)
        bin_dir = Path(__file__).with_name("bin")
        for name in (
            f"philips-camera-bridge-{osname}-{arch}{ext}",
            f"philips-camera-bridge-linux-{arch}",
        ):
            local = bin_dir / name
            if local.is_file():
                self._make_executable(local)
                return local
        # 2) cached download (lives under config so it survives integration updates)
        cache_dir = Path(self.hass.config.path(".philips_pet_series", "bin"))
        cached = cache_dir / f"philips-camera-bridge-{BRIDGE_BINARY_TAG}-{osname}-{arch}{ext}"
        if cached.is_file():
            self._make_executable(cached)
            return cached
        # 3) download the matching release asset + verify its checksum
        asset = f"tuya-ipc-terminal-{osname}-{arch}{ext}"
        base = f"https://github.com/{BRIDGE_BINARY_REPO}/releases/download/{BRIDGE_BINARY_TAG}"
        await self._download_verified(f"{base}/{asset}", f"{base}/checksums.txt", asset, cached)
        self._make_executable(cached)
        return cached

    async def _download_verified(
        self, url: str, checksums_url: str, asset: str, dest: Path
    ) -> None:
        session = async_get_clientsession(self.hass)
        _LOGGER.info("Downloading camera bridge %s", asset)
        async with session.get(checksums_url, raise_for_status=True) as resp:
            checksums = await resp.text()
        want = None
        for line in checksums.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].lstrip("*") == asset:
                want = parts[0].lower()
                break
        if want is None:
            raise RuntimeError(f"no checksum for {asset} in release {BRIDGE_BINARY_TAG}")
        async with session.get(url, raise_for_status=True) as resp:
            data = await resp.read()
        got = hashlib.sha256(data).hexdigest()
        if got != want:
            raise RuntimeError(f"camera bridge checksum mismatch for {asset}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        tmp.write_bytes(data)
        tmp.replace(dest)
        _LOGGER.info("Camera bridge %s ready (%d bytes)", asset, len(data))


DOMAIN_LOG_PREFIX = "philips-pet-camera-bridge"
