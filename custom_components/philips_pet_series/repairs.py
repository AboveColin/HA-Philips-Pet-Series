"""Repair flow for a feeder that the account no longer lists.

A feeder that moves from the Philips Pet Series app to the HomeID app, or is
paired again, gets a new Philips device id. The flow moves the entities of the
old device to the new device, so the entity ids, the history and the
dashboards stay. It can also create the saved meal schedule again, because the
app removes the meals of a feeder when the feeder leaves a home.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers import selector

from petsseries.models import Meal

from . import migration
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

REMOVE = "remove"


def _entry_data(hass: HomeAssistant, entry_id: str) -> dict[str, Any]:
    return hass.data.get(DOMAIN, {}).get(entry_id) or {}


def _new_unique_ids(hass: HomeAssistant, entry_id: str, device_id: str) -> set[str]:
    entity_registry = er.async_get(hass)
    prefix = f"{device_id}_"
    return {
        e.unique_id
        for e in er.async_entries_for_config_entry(entity_registry, entry_id)
        if e.unique_id.startswith(prefix)
    }


def _registry_device(
    device_registry: dr.DeviceRegistry, entry_id: str, device_id: str
) -> dr.DeviceEntry | None:
    """Return the registry device of a Philips device id in this entry."""
    lookup = getattr(device_registry, "async_get_device_by_identifier", None)
    if lookup is not None:
        return lookup((DOMAIN, device_id), entry_id)
    # Older Home Assistant versions have only the lookup across all entries.
    return device_registry.async_get_device(identifiers={(DOMAIN, device_id)})


def _remove_from_entry(
    device_registry: dr.DeviceRegistry, device_entry_id: str, entry_id: str
) -> None:
    """Remove a device from this entry only.

    A feeder with a MAC address can share its registry device with a router
    integration. Home Assistant removes the device when no entry is left.
    """
    device_registry.async_update_device(device_entry_id, remove_config_entry_id=entry_id)


class DeviceGoneRepairFlow(RepairsFlow):
    """Move the entities of a gone feeder to its new device, or remove it."""

    def __init__(self, issue_id: str, entry_id: str, device_id: str) -> None:
        self._issue_id = issue_id
        self._entry_id = entry_id
        self._device_id = device_id
        self._saved: dict[str, Any] | None = None

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        # Home Assistant calls this step with the start data of the flow, not
        # with form answers, so the form is in the next step.
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        coordinator = _entry_data(self.hass, self._entry_id).get("coordinator")
        if coordinator is None:
            return self.async_abort(reason="not_loaded")
        old = dr.async_get(self.hass).async_get(self._device_id)
        old_id = None if old is None else migration.philips_device_id(old.identifiers, DOMAIN)
        if old is None or old_id is None:
            ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)
            return self.async_abort(reason="device_gone")

        data = coordinator.data or {}
        current = list(data.get("devices", []))
        if any(str(d.id) == old_id for d in current):
            ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)
            return self.async_abort(reason="device_back")

        registered = {
            pid
            for d in dr.async_entries_for_config_entry(dr.async_get(self.hass), self._entry_id)
            if (pid := migration.philips_device_id(d.identifiers, DOMAIN))
        }
        replacements = migration.candidates(old.model, current, registered)
        self._saved = (await coordinator.async_load_saved_meals()).get(old_id)
        meals = (self._saved or {}).get("meals") or []

        if user_input is not None:
            target = user_input["target"]
            if target == REMOVE:
                return await self._async_remove(coordinator, old, old_id)
            restore = bool(user_input.get("restore_meals")) and bool(meals)
            return await self._async_move(old, old_id, target, restore)

        options = [
            selector.SelectOptionDict(
                value=str(d.id),
                label=f"Move to {d.name} ({d.product_ctn})",
            )
            for d in replacements
        ]
        options.append(selector.SelectOptionDict(value=REMOVE, label="Remove the old device only"))
        schema: dict[Any, Any] = {
            vol.Required("target", default=options[0]["value"]): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options, mode=selector.SelectSelectorMode.LIST
                )
            )
        }
        if meals and replacements:
            schema[vol.Optional("restore_meals", default=True)] = selector.BooleanSelector()

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema(schema),
            description_placeholders={
                "name": old.name_by_user or old.name or old_id,
                "meals": migration.describe(meals) if meals else "(no saved meals)",
                "saved_at": (self._saved or {}).get("saved_at", "-"),
            },
        )

    async def _async_remove(self, coordinator, old: dr.DeviceEntry, old_id: str) -> FlowResult:
        """Remove the old device and its entities."""
        _remove_from_entry(dr.async_get(self.hass), old.id, self._entry_id)
        await coordinator.async_forget_meals(old_id)
        ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)
        return self.async_create_entry(data={})

    async def _async_move(
        self, old: dr.DeviceEntry, old_id: str, new_id: str, restore: bool
    ) -> FlowResult:
        """Give the old entities the unique ids of the new device."""
        hass = self.hass
        entity_registry = er.async_get(hass)
        device_registry = dr.async_get(hass)

        new_unique_ids = _new_unique_ids(hass, self._entry_id, new_id)
        new_device = _registry_device(device_registry, self._entry_id, new_id)
        if not new_unique_ids or new_device is None:
            # The new device came after the entry was set up, so it has no
            # entities yet. A reload creates them.
            await hass.config_entries.async_reload(self._entry_id)
            new_unique_ids = _new_unique_ids(hass, self._entry_id, new_id)
            new_device = _registry_device(device_registry, self._entry_id, new_id)
        if new_device is None:
            return self.async_abort(reason="new_device_missing")

        old_entities = er.async_entries_for_device(
            entity_registry, old.id, include_disabled_entities=True
        )
        old_entities = [e for e in old_entities if e.config_entry_id == self._entry_id]
        moves, drops = migration.unique_id_moves(
            old_id, new_id, [e.unique_id for e in old_entities], new_unique_ids
        )
        by_unique_id = {e.unique_id: e for e in old_entities}
        for old_unique_id, new_unique_id in moves.items():
            entity = by_unique_id[old_unique_id]
            clash = entity_registry.async_get_entity_id(entity.domain, DOMAIN, new_unique_id)
            if clash is not None:
                entity_registry.async_remove(clash)
            entity_registry.async_update_entity(
                entity.entity_id, new_unique_id=new_unique_id, device_id=new_device.id
            )
        for unique_id in drops:
            entity_registry.async_remove(by_unique_id[unique_id].entity_id)

        device_registry.async_update_device(
            new_device.id,
            area_id=new_device.area_id or old.area_id,
            name_by_user=new_device.name_by_user or old.name_by_user,
        )
        _remove_from_entry(device_registry, old.id, self._entry_id)
        _LOGGER.info(
            "Moved %d entities from device %s to device %s, removed %d",
            len(moves), old_id, new_id, len(drops),
        )
        await hass.config_entries.async_reload(self._entry_id)

        failed: list[str] = []
        coordinator = _entry_data(hass, self._entry_id).get("coordinator")
        if restore and coordinator is not None:
            client = _entry_data(hass, self._entry_id).get("client")
            failed = await self._async_restore_meals(coordinator, client, new_id)
            await coordinator.async_request_refresh()
        if coordinator is not None and not failed:
            await coordinator.async_forget_meals(old_id)
        ir.async_delete_issue(hass, DOMAIN, self._issue_id)
        if failed:
            return self.async_abort(
                reason="meals_failed", description_placeholders={"failed": ", ".join(failed)}
            )
        return self.async_create_entry(data={})

    async def _async_restore_meals(self, coordinator, client, new_id: str) -> list[str]:
        """Create the saved meals on the new device. Return the failed times."""
        data = coordinator.data or {}
        homes = {home.id: home for home in data.get("homes", [])}
        home = next(
            (
                homes.get(home_id)
                for home_id, devices in data.get("home_devices", {}).items()
                if any(str(d.id) == new_id for d in devices)
            ),
            None,
        )
        records = (self._saved or {}).get("meals") or []
        if home is None:
            return [r["time"] for r in records]
        taken = {
            t
            for m in data.get("meals", [])
            if str(m.device_id) == new_id and (t := migration.wire_time(m.feed_time))
        }
        failed: list[str] = []
        for record in migration.meals_to_restore(records, taken):
            meal = Meal(
                id="",
                name=record["name"],
                portion_amount=record["amount"],
                feed_time=record["time"],
                repeat_days=record["repeat_days"] or None,
                device_id=new_id,
                enabled=True,
                url="",
            )
            try:
                created = await client.meals.create_meal(home, meal)
                if not record.get("enabled", True):
                    await client.meals.set_meal_enabled(home, created.id, False)
            except Exception as err:  # noqa: BLE001 - report each meal, then go on
                _LOGGER.warning("Could not create the meal at %s: %s", record["time"], err)
                failed.append(record["time"])
        return failed


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None
) -> RepairsFlow:
    """Return the repair flow for an issue of this integration."""
    data = data or {}
    return DeviceGoneRepairFlow(issue_id, str(data.get("entry_id")), str(data.get("device_id")))
