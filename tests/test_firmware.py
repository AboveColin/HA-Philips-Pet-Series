"""Tests for the firmware and OTA lookups.

`firmware.py` deliberately imports nothing from Home Assistant, so these run
under plain pytest with no test harness.

The fallback chain in `installed_version` is the part worth testing: the Tuya OTA
endpoints are unauthorised for most third-party logins, so in practice the
version comes from a different source on almost every install, and there is no
way to notice a broken rung by looking at one device.
"""

import importlib.util
from pathlib import Path

import pytest

# Loaded straight from the file rather than as `philips_pet_series.firmware`,
# because importing the package runs its __init__, which needs Home Assistant.
# Keeping this import path is what lets the suite run anywhere.
_MODULE = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "philips_pet_series"
    / "firmware.py"
)
_spec = importlib.util.spec_from_file_location("pps_firmware", _MODULE)
firmware = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(firmware)


class FakeCoordinator:
    """Just enough of the coordinator: it is only ever read from."""

    def __init__(self, data):
        self.data = data


class FakeDevice:
    def __init__(self, device_id="dev1", **attrs):
        self.id = device_id
        for key, value in attrs.items():
            setattr(self, key, value)


def definition(**ota_modules):
    """A device_definitions payload shaped like Tuya's."""
    return {
        "dev1": {
            "verSw": "definition-version",
            "otaInfo": {"otaModuleMap": ota_modules},
        }
    }


# --- ota_record -------------------------------------------------------------


def test_record_is_matched_by_module_type():
    """wifi is OTA type 0 and mcu is 9; a record for one is not the other."""
    coordinator = FakeCoordinator(
        {
            "firmware_info": {
                "dev1": [
                    {"type": 0, "version": "wifi-1"},
                    {"type": 9, "version": "mcu-1"},
                ]
            }
        }
    )
    wifi, _ = firmware.ota_record(coordinator, "dev1", "wifi")
    mcu, _ = firmware.ota_record(coordinator, "dev1", "mcu")
    assert wifi["version"] == "wifi-1"
    assert mcu["version"] == "mcu-1"


def test_history_is_only_consulted_when_live_records_are_empty():
    live = {"type": 0, "version": "live"}
    stored = {"type": 0, "version": "stored"}

    with_live = FakeCoordinator(
        {"firmware_info": {"dev1": [live]}, "ota_history": {"dev1": [stored]}}
    )
    record, from_history = firmware.ota_record(with_live, "dev1", "wifi")
    assert record["version"] == "live"
    assert from_history is False

    without_live = FakeCoordinator({"ota_history": {"dev1": [stored]}})
    record, from_history = firmware.ota_record(without_live, "dev1", "wifi")
    assert record["version"] == "stored"
    assert from_history is True


def test_unparseable_record_type_is_skipped_not_raised():
    coordinator = FakeCoordinator(
        {
            "firmware_info": {
                "dev1": [{"type": "junk"}, {"type": 0, "version": "good"}]
            }
        }
    )
    record, _ = firmware.ota_record(coordinator, "dev1", "wifi")
    assert record["version"] == "good"


def test_unknown_component_has_no_record():
    coordinator = FakeCoordinator({"firmware_info": {"dev1": [{"type": 0}]}})
    assert firmware.ota_record(coordinator, "dev1", "bluetooth") == ({}, False)


# --- installed_version fallback chain ---------------------------------------


def test_ota_record_current_version_wins():
    coordinator = FakeCoordinator(
        {
            "firmware_info": {
                "dev1": [{"type": 0, "currentVersion": "from-record"}]
            },
            "device_definitions": definition(wifi={"verSw": "from-module"}),
        }
    )
    assert (
        firmware.installed_version(coordinator, FakeDevice(), "wifi") == "from-record"
    )


def test_falls_back_to_the_module_map():
    coordinator = FakeCoordinator(
        {"device_definitions": definition(wifi={"verSw": "from-module"})}
    )
    assert (
        firmware.installed_version(coordinator, FakeDevice(), "wifi") == "from-module"
    )


def test_definition_version_is_used_for_wifi_only():
    """`verSw` on the device record is the wireless module's version.

    Reading it for the MCU would report the wrong chip's firmware, which is
    worse than reporting nothing.
    """
    coordinator = FakeCoordinator({"device_definitions": definition()})
    assert (
        firmware.installed_version(coordinator, FakeDevice(), "wifi")
        == "definition-version"
    )
    assert firmware.installed_version(coordinator, FakeDevice(), "mcu") is None


def test_falls_back_to_a_device_attribute():
    coordinator = FakeCoordinator({})
    device = FakeDevice(mcu_version="from-device")
    assert firmware.installed_version(coordinator, device, "mcu") == "from-device"


@pytest.mark.parametrize("key", ["wifiVersion", "wifi_version", "wifi"])
def test_falls_back_to_tuya_status_under_any_spelling(key):
    coordinator = FakeCoordinator(
        {"settings": {"dev1": {"tuya_status": {key: 42}}}}
    )
    assert firmware.installed_version(coordinator, FakeDevice(), "wifi") == "42"


def test_nothing_known_reports_nothing():
    assert firmware.installed_version(FakeCoordinator({}), FakeDevice(), "wifi") is None


def test_a_non_dict_tuya_status_does_not_raise():
    """The fallback status dict is sometimes a list of code/value pairs."""
    coordinator = FakeCoordinator({"settings": {"dev1": {"tuya_status": []}}})
    assert firmware.installed_version(coordinator, FakeDevice(), "wifi") is None


# --- offered_version --------------------------------------------------------


def test_no_offer_while_upgrade_status_is_zero():
    """The state every one of these feeders is actually in.

    Tuya publishes a package URL only while upgradeStatus is non-zero, so a
    record carrying a version but status 0 is not an offer.
    """
    coordinator = FakeCoordinator(
        {
            "firmware_info": {
                "dev1": [{"type": 0, "version": "111.06.24", "upgradeStatus": 0}]
            }
        }
    )
    assert firmware.offered_version(coordinator, FakeDevice(), "wifi") is None


def test_an_offer_reports_its_version():
    coordinator = FakeCoordinator(
        {
            "firmware_info": {
                "dev1": [{"type": 0, "version": "111.07.00", "upgradeStatus": 1}]
            }
        }
    )
    assert (
        firmware.offered_version(coordinator, FakeDevice(), "wifi") == "111.07.00"
    )


def test_an_offer_without_a_version_is_not_an_offer():
    coordinator = FakeCoordinator(
        {"firmware_info": {"dev1": [{"type": 0, "upgradeStatus": 1}]}}
    )
    assert firmware.offered_version(coordinator, FakeDevice(), "wifi") is None


def test_unparseable_upgrade_status_is_not_an_offer():
    coordinator = FakeCoordinator(
        {
            "firmware_info": {
                "dev1": [{"type": 0, "version": "x", "upgradeStatus": None}]
            }
        }
    )
    assert firmware.offered_version(coordinator, FakeDevice(), "wifi") is None


# --- has_ota_module ---------------------------------------------------------


def test_module_presence_requires_a_version():
    """An empty module entry is not a module.

    The MCU entities are created off this, and a feeder without a separate
    microcontroller would otherwise get a permanently empty entity.
    """
    coordinator = FakeCoordinator({"device_definitions": definition(mcu={})})
    assert firmware.has_ota_module(coordinator, FakeDevice(), "mcu") is False

    coordinator = FakeCoordinator({"device_definitions": definition(mcu={"verSw": "1"})})
    assert firmware.has_ota_module(coordinator, FakeDevice(), "mcu") is True


# --- called before the first refresh ---------------------------------------


@pytest.mark.parametrize("coordinator", [FakeCoordinator(None), None])
def test_survives_being_asked_before_any_data_arrived(coordinator):
    """The stale-entity sweep runs before the first refresh has landed."""
    assert firmware.has_ota_module(coordinator, FakeDevice(), "mcu") is False
    assert firmware.installed_version(coordinator, FakeDevice(), "wifi") is None
    assert firmware.offered_version(coordinator, FakeDevice(), "wifi") is None
