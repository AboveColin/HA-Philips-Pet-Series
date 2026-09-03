"""Shared firmware and OTA lookups.

The firmware sensors and the update entities need the same three things out of
the coordinator: what the device reports it is running, what Tuya has on offer,
and the raw OTA record behind both.  Keeping that here means the two can never
disagree about a version.
"""

from __future__ import annotations

# Tuya's OTA record "type", per module.  The wireless module and the MCU are
# offered separately, so a record for one says nothing about the other.
_OTA_TYPES = {"wifi": 0, "mcu": 9}

# Observed values of "upgradeStatus": 0 means nothing is on offer, and Tuya only
# publishes the package URL while it is non-zero.  1 is an offer.  Higher values
# presumably describe an update in flight, but none has ever been seen on these
# feeders, so nothing here pretends to know what they mean.
STATUS_UPDATE_AVAILABLE = 1


def _upgrade_status(record) -> int | None:
    """``upgradeStatus`` as an int, or None when absent or unparseable.

    Tuya has been seen returning this field as a number and as a numeric
    string, so both callers have to agree on how it is read or they will
    disagree about whether an update exists.
    """
    raw = record.get("upgradeStatus")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def is_offer(record) -> bool:
    """Whether this record describes an update Tuya is currently offering."""
    return _upgrade_status(record) == STATUS_UPDATE_AVAILABLE


def _data(coordinator) -> dict:
    """The coordinator's payload, or an empty one.

    Called from the stale-entity sweep as well as from entities, and that runs
    early enough that the first refresh may not have landed yet.
    """
    return getattr(coordinator, "data", None) or {}


def device_definition(coordinator, device_id) -> dict:
    """Tuya device metadata (``thing.m.device.get``) for one device."""
    definition = _data(coordinator).get("device_definitions", {}).get(device_id)
    return definition if isinstance(definition, dict) else {}


def ota_module(coordinator, device_id, component: str) -> dict:
    """Per-module OTA record, when the device reports one.

    Devices expose ``otaInfo.otaModuleMap`` keyed by module name ("wifi",
    "mcu").  Feeders without a separate microcontroller list only "wifi", in
    which case there is genuinely no MCU version to report.
    """
    ota_info = device_definition(coordinator, device_id).get("otaInfo")
    if not isinstance(ota_info, dict):
        return {}
    module_map = ota_info.get("otaModuleMap")
    if not isinstance(module_map, dict):
        return {}
    module = module_map.get(component)
    return module if isinstance(module, dict) else {}


def has_ota_module(coordinator, device, component: str) -> bool:
    """Whether the device's metadata reports an OTA module by this name."""
    return bool(ota_module(coordinator, device.id, component).get("verSw"))


def reports_ota_modules(coordinator, device_id) -> bool:
    """Whether we actually have this device's module list.

    False means "we do not know", which is not the same as "the device has no
    such module".  Anything destructive has to tell those two apart: a metadata
    fetch that failed once would otherwise look like hardware that lost a
    component.
    """
    ota_info = device_definition(coordinator, device_id).get("otaInfo")
    return isinstance(ota_info, dict) and isinstance(
        ota_info.get("otaModuleMap"), dict
    )


def ota_record(
    coordinator, device_id, component: str, *, include_history: bool = True
) -> tuple[dict, bool]:
    """The OTA record for a component, and whether it came from stored history.

    Returns ``({}, False)`` when Tuya has told us nothing about this module.
    History is only consulted when the live endpoints returned nothing, because
    a signed package URL is short-lived and worth keeping once seen.

    Pass ``include_history=False`` for any question about the present.  A stored
    record is a snapshot of something Tuya said once, so it cannot establish
    what is true now.
    """
    wanted = _OTA_TYPES.get(component)
    if wanted is None:
        return {}, False

    data = _data(coordinator)
    records = data.get("firmware_info", {}).get(device_id, []) + (
        data.get("product_firmware_info", {}).get(device_id, [])
    )
    from_history = not records
    if from_history:
        records = data.get("ota_history", {}).get(device_id, []) if include_history else []

    for record in records:
        try:
            if int(record.get("type", -1)) == wanted:
                return record, from_history
        except (TypeError, ValueError):
            continue
    return {}, False


def installed_version(coordinator, device, component: str) -> str | None:
    """The version this module is currently running, from the best source.

    The OTA endpoints are frequently unauthorised for third-party logins, so
    this walks from the most authoritative source to the least rather than
    trusting any single one.  Every live source is tried before the stored one,
    because a kept record can be arbitrarily old and would otherwise pin the
    version to whatever it said months ago.
    """
    live, _ = ota_record(coordinator, device.id, component, include_history=False)
    version = live.get("currentVersion") or live.get("current_version")
    if version:
        return version

    module_version = ota_module(coordinator, device.id, component).get("verSw")
    if module_version:
        return module_version

    if component == "wifi":
        # ``verSw`` on the device record is the wireless module firmware, which
        # is the version the Philips app shows for the device.
        definition_version = device_definition(coordinator, device.id).get("verSw")
        if definition_version:
            return definition_version

    value = getattr(device, f"{component}_version", None)
    if value:
        return value

    status = _data(coordinator).get("settings", {}).get(device.id, {}).get(
        "tuya_status", {}
    )
    if isinstance(status, dict):
        for key in (f"{component}Version", f"{component}_version", component):
            if status.get(key) is not None:
                return str(status[key])

    # Last resort: a record kept from an earlier offer.  Better than reporting
    # nothing, but every live source above is preferred over it.
    stored, _ = ota_record(coordinator, device.id, component)
    return stored.get("currentVersion") or stored.get("current_version") or None


def offered_version(coordinator, device, component: str) -> str | None:
    """The version Tuya is offering right now, or None.

    Live records only.  A stored record that once carried an offer would
    otherwise keep claiming an update forever, long after Philips stopped
    serving it.
    """
    record, _ = ota_record(coordinator, device.id, component, include_history=False)
    if not record or not is_offer(record):
        return None
    return record.get("version") or None
