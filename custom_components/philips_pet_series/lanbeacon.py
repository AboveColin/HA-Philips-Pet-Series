"""Locate feeders on the local network from their Tuya broadcast.

Tuya devices announce themselves on UDP 6667 every few seconds. The payload is
AES-ECB encrypted with a key published in Tuya's own SDK, and carries the
device's ``gwId`` -- the same identifier the cloud API calls ``vendorId`` -- so a
beacon can be matched to a configured device exactly, with no guesswork about
MAC prefixes or hostnames.

This is passive: nothing is ever sent to the device. It provides the device's
current LAN address (which survives DHCP changes) and a genuine "is it on the
network" signal, independent of the cloud.

Important: a Home Assistant container on Docker's default bridge network does
not receive LAN broadcasts, so no beacon will ever arrive there. Absence of a
beacon therefore means "no information", never "the device is offline" --
callers must treat :meth:`BeaconListener.seen` returning ``None`` as unknown.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import json
import logging
import time

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_LOGGER = logging.getLogger(__name__)

BEACON_PORT = 6667
# Published in Tuya's SDK for the discovery broadcast; not device-specific.
_BROADCAST_KEY = hashlib.md5(b"yGAdlopoPVldABfn").digest()
_HEADER = 20
_TRAILER = 8

# Beacons arrive roughly every 5s; allow generous slack for a missed few.
STALE_AFTER = 60.0


@dataclass
class Beacon:
    """The last announcement seen from one device."""

    ip: str
    at: float
    protocol: str | None = None

    @property
    def age(self) -> float:
        return time.monotonic() - self.at

    @property
    def fresh(self) -> bool:
        return self.age <= STALE_AFTER


def _decrypt(packet: bytes) -> dict | None:
    """Return the beacon's JSON payload, or None if it is not one of ours."""
    if len(packet) <= _HEADER + _TRAILER:
        return None
    body = packet[_HEADER:-_TRAILER]
    if len(body) % 16:
        return None
    try:
        decryptor = Cipher(algorithms.AES(_BROADCAST_KEY), modes.ECB()).decryptor()
        plain = decryptor.update(body) + decryptor.finalize()
    except Exception:
        return None
    if plain and plain[-1] <= 16:
        plain = plain[: -plain[-1]]
    try:
        payload = json.loads(plain.decode("utf-8", "replace"))
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


class _Protocol(asyncio.DatagramProtocol):
    def __init__(self, listener: BeaconListener) -> None:
        self._listener = listener

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        payload = _decrypt(data)
        if not payload:
            return
        device_id = payload.get("gwId") or payload.get("devId")
        if not device_id:
            return
        self._listener._record(
            str(device_id),
            str(payload.get("ip") or addr[0]),
            payload.get("version"),
        )

    def error_received(self, exc: Exception) -> None:  # pragma: no cover
        _LOGGER.debug("Beacon socket error: %s", exc)


class BeaconListener:
    """Passively track which feeders are announcing themselves on the LAN."""

    def __init__(self) -> None:
        self._beacons: dict[str, Beacon] = {}
        self._transport: asyncio.BaseTransport | None = None

    @property
    def listening(self) -> bool:
        """Whether the socket is open. False means we know nothing at all."""
        return self._transport is not None

    def _record(self, device_id: str, ip: str, protocol) -> None:
        previous = self._beacons.get(device_id)
        if previous is None or previous.ip != ip:
            _LOGGER.debug("Feeder %s announced itself at %s", device_id, ip)
        self._beacons[device_id] = Beacon(
            ip=ip,
            at=time.monotonic(),
            protocol=str(protocol) if protocol is not None else None,
        )

    @property
    def any_seen(self) -> bool:
        """Whether any device has ever announced itself.

        Distinguishes "this feeder is away" from "broadcasts never reach us".
        """
        return bool(self._beacons)

    def seen(self, device_id: str | None) -> Beacon | None:
        """Return the last fresh beacon for a device, else None (= unknown)."""
        if not device_id:
            return None
        beacon = self._beacons.get(str(device_id))
        return beacon if beacon is not None and beacon.fresh else None

    async def async_start(self) -> None:
        """Open the listening socket, tolerating hosts that cannot listen."""
        if self._transport is not None:
            return
        loop = asyncio.get_running_loop()
        try:
            transport, _ = await loop.create_datagram_endpoint(
                lambda: _Protocol(self),
                local_addr=("0.0.0.0", BEACON_PORT),
                reuse_port=True,
                allow_broadcast=True,
            )
        except Exception as err:
            # Another process may hold the port, or the platform may refuse it.
            # This is optional enrichment, so carry on without it.
            _LOGGER.debug("Not listening for feeder beacons: %s", err)
            return
        self._transport = transport
        _LOGGER.debug("Listening for feeder beacons on udp/%s", BEACON_PORT)

    def async_stop(self) -> None:
        if self._transport is not None:
            self._transport.close()
            self._transport = None
        self._beacons.clear()
