"""Serve the bundled Lovelace cards and register them as resources.

HACS allows a repository exactly one category, so this repository cannot be
both an "integration" and a "plugin".  The cards therefore ship inside the
integration: the files in this package are served over HTTP and registered as
Lovelace resources automatically, so a user who installs the integration gets
`custom:philips-feeder-card` without adding a resource by hand.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_call_later

from ..const import JSMODULES, URL_BASE

_LOGGER = logging.getLogger(__name__)

# How long to keep waiting for Lovelace to finish loading its resource store
# before giving up.  Resources normally load within a second of startup; this is
# a tripwire, not a timeout anyone should ever reach.
_RESOURCE_WAIT_INTERVAL = 5
_RESOURCE_WAIT_ATTEMPTS = 12


class JSModuleRegistration:
    """Serve the card bundle and keep its Lovelace resource up to date."""

    def __init__(self, hass: HomeAssistant, version: str) -> None:
        """Initialise the registrar for a given integration version."""
        self.hass = hass
        self.version = version

    @property
    def lovelace_resources(self):
        """Return the Lovelace resource collection, or None if not set up yet."""
        lovelace = self.hass.data.get("lovelace")
        if lovelace is None:
            return None
        # Object-based in modern Home Assistant, dict-based in older releases.
        if hasattr(lovelace, "resources"):
            return lovelace.resources
        if isinstance(lovelace, dict):
            return lovelace.get("resources")
        return None

    async def async_register(self) -> None:
        """Serve the bundle, then register it in storage-mode Lovelace."""
        await self._async_register_path()
        await self._async_wait_for_lovelace_resources()

    def _log_manual_instructions(self, reason: str) -> None:
        """Explain exactly which resource to add when we cannot add it."""
        for module in JSMODULES:
            _LOGGER.info(
                "%s, so the Philips Pet Series cards were not registered "
                "automatically. Add this Lovelace resource by hand to use "
                "them: url: %s/%s?v=%s, type: module",
                reason,
                URL_BASE,
                module["filename"],
                self.version,
            )

    async def _async_register_path(self) -> None:
        """Register the static HTTP path that serves the card files."""
        frontend_path = Path(__file__).parent
        try:
            await self.hass.http.async_register_static_paths(
                [StaticPathConfig(URL_BASE, str(frontend_path), False)]
            )
        except RuntimeError:
            # Already registered by a previous config entry; nothing to do.
            _LOGGER.debug("Static path %s already registered", URL_BASE)
        else:
            _LOGGER.debug("Serving %s from %s", URL_BASE, frontend_path)

    async def _async_wait_for_lovelace_resources(self) -> None:
        """Register modules once Lovelace has loaded its resource store.

        Lovelace may not have set up yet when this entry does, and "not set up
        yet" looks exactly like "running in YAML mode" from here.  Retrying
        keeps the two apart: a YAML-mode instance still has no resource
        collection after the wait, a slow-starting one does.
        """
        attempts = 0

        async def _check_loaded(_now=None) -> None:
            nonlocal attempts
            resources = self.lovelace_resources
            if resources is not None:
                # Only the storage-backed collection is writable.  Asking the
                # collection what it can do beats reading a mode string: the
                # field naming that string has changed across releases, the
                # methods have not.
                if hasattr(resources, "async_create_item"):
                    # Forces the collection to read its store, so async_items()
                    # below reflects what is really registered instead of an
                    # empty not-yet-loaded list -- which would re-add the
                    # resource on every restart.
                    await resources.async_get_info()
                    await self._async_register_modules(resources)
                else:
                    # YAML mode owns its own resource list by design.
                    self._log_manual_instructions("Lovelace is in YAML mode")
                return

            attempts += 1
            if attempts >= _RESOURCE_WAIT_ATTEMPTS:
                self._log_manual_instructions(
                    f"Lovelace resources were still unavailable after "
                    f"{_RESOURCE_WAIT_INTERVAL * _RESOURCE_WAIT_ATTEMPTS}s"
                )
                return
            async_call_later(self.hass, _RESOURCE_WAIT_INTERVAL, _check_loaded)

        await _check_loaded()

    async def _async_register_modules(self, resources) -> None:
        """Create or version-bump the Lovelace resource for each module."""
        existing = [
            resource
            for resource in resources.async_items()
            if _strip_version(resource["url"]).startswith(URL_BASE)
        ]

        for module in JSMODULES:
            url = f"{URL_BASE}/{module['filename']}"
            current = next(
                (r for r in existing if _strip_version(r["url"]) == url), None
            )
            if current is None:
                await resources.async_create_item(
                    {"res_type": "module", "url": f"{url}?v={self.version}"}
                )
                _LOGGER.info("Registered %s v%s", module["name"], self.version)
                continue

            # The version query parameter is what busts the browser cache, so
            # rewriting it on upgrade is what makes a new card version load.
            if _version_of(current["url"]) != self.version:
                await resources.async_update_item(
                    current["id"],
                    {"res_type": "module", "url": f"{url}?v={self.version}"},
                )
                _LOGGER.info("Updated %s to v%s", module["name"], self.version)

    async def async_unregister(self) -> None:
        """Remove the Lovelace resources this integration created."""
        resources = self.lovelace_resources
        if resources is None or not hasattr(resources, "async_delete_item"):
            return
        await resources.async_get_info()
        for module in JSMODULES:
            url = f"{URL_BASE}/{module['filename']}"
            for resource in [
                r for r in resources.async_items() if _strip_version(r["url"]) == url
            ]:
                await resources.async_delete_item(resource["id"])
                _LOGGER.info("Unregistered %s", module["name"])


def _strip_version(url: str) -> str:
    """Return the resource URL without its query string."""
    return url.split("?")[0]


def _version_of(url: str) -> str:
    """Return the ``?v=`` value of a resource URL, or "0" when absent."""
    _, _, query = url.partition("?")
    if query.startswith("v="):
        return query[2:]
    return "0"
