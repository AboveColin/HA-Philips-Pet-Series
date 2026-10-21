"""Tests for the decisions behind the "feeder has a new device id" repair.

The repair moves entities and creates meals on a real feeder, so each decision
is checked on its own: which device is gone, what can replace it, which
entities move, and which meals are created again.
"""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

# Loaded straight from the file, for the same reason as in test_firmware.py.
_MODULE = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "philips_pet_series"
    / "migration.py"
)
_spec = importlib.util.spec_from_file_location("pps_migration", _MODULE)
migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migration)

DOMAIN = "philips_pet_series"


def device(device_id, ctn="PAW5320", name="Feeder"):
    return SimpleNamespace(id=device_id, product_ctn=ctn, name=name)


def meal(device_id, time, amount=1, name="Meal", days=(1, 2, 3, 4, 5, 6, 7), enabled=True):
    return SimpleNamespace(
        device_id=device_id,
        feed_time=time,
        portion_amount=amount,
        name=name,
        repeat_days=list(days),
        enabled=enabled,
    )


class TestPhilipsDeviceId:
    def test_a_feeder_identifier_gives_its_id(self):
        assert migration.philips_device_id({(DOMAIN, "old-1")}, DOMAIN) == "old-1"

    def test_a_home_device_is_not_a_feeder(self):
        assert migration.philips_device_id({(DOMAIN, "home_h1")}, DOMAIN) is None

    def test_an_identifier_of_another_integration_is_ignored(self):
        assert migration.philips_device_id({("mqtt", "old-1")}, DOMAIN) is None


class TestCandidates:
    def test_only_the_same_product_can_take_the_place(self):
        current = [device("new-1"), device("fountain", ctn="PAW5610")]
        assert [d.id for d in migration.candidates("PAW5320", current, set())] == ["new-1"]

    def test_a_device_new_to_home_assistant_comes_first(self):
        # The second feeder of the same model is already in the registry; the
        # moved one is not.
        current = [device("other", name="A"), device("new-1", name="B")]
        result = migration.candidates("PAW5320", current, {"other"})
        assert [d.id for d in result] == ["new-1", "other"]

    def test_an_old_device_without_a_model_has_no_candidates(self):
        assert migration.candidates(None, [device("new-1")], set()) == []


class TestUniqueIdMoves:
    def test_an_entity_the_new_device_also_has_moves(self):
        moves, drops = migration.unique_id_moves(
            "old-1",
            "new-1",
            ["old-1_camera", "old-1_feed_button"],
            {"new-1_camera", "new-1_feed_button"},
        )
        assert moves == {"old-1_camera": "new-1_camera", "old-1_feed_button": "new-1_feed_button"}
        assert drops == []

    def test_an_entity_the_new_device_lacks_is_dropped(self):
        moves, drops = migration.unique_id_moves(
            "old-1", "new-1", ["old-1_mcu_firmware_version"], {"new-1_camera"}
        )
        assert moves == {}
        assert drops == ["old-1_mcu_firmware_version"]

    def test_only_the_prefix_is_replaced(self):
        # A suffix can hold the old id too; only the leading one is the device.
        moves, _ = migration.unique_id_moves(
            "d1", "d2", ["d1_tuya_dp_d1"], {"d2_tuya_dp_d1"}
        )
        assert moves == {"d1_tuya_dp_d1": "d2_tuya_dp_d1"}


class TestSchedules:
    def test_meals_are_grouped_per_device_and_sorted_by_time(self):
        result = migration.schedules(
            [device("d1"), device("d2")],
            [meal("d1", "18:00", 2), meal("d1", "06:00"), meal("d2", "12:00")],
        )
        assert [r["time"] for r in result["d1"]] == ["06:00", "18:00"]
        assert [r["time"] for r in result["d2"]] == ["12:00"]

    def test_a_device_without_meals_has_an_empty_schedule(self):
        assert migration.schedules([device("d1")], []) == {"d1": []}

    def test_a_meal_of_an_unknown_device_is_ignored(self):
        assert migration.schedules([device("d1")], [meal("gone", "06:00")]) == {"d1": []}

    def test_seconds_and_a_zone_letter_are_cut_from_the_time(self):
        result = migration.schedules([device("d1")], [meal("d1", "6:05:00Z")])
        assert result["d1"][0]["time"] == "06:05"


class TestMergeSaved:
    def test_a_new_schedule_is_saved(self):
        saved = {}
        current = migration.schedules([device("d1")], [meal("d1", "06:00")])
        assert migration.merge_saved(saved, current, {"d1": "Feeder"}, "t1") is True
        assert saved["d1"]["saved_at"] == "t1"
        assert saved["d1"]["name"] == "Feeder"

    def test_an_unchanged_schedule_keeps_its_date(self):
        current = migration.schedules([device("d1")], [meal("d1", "06:00")])
        saved = {}
        migration.merge_saved(saved, current, {}, "t1")
        assert migration.merge_saved(saved, current, {}, "t2") is False
        assert saved["d1"]["saved_at"] == "t1"

    def test_an_empty_schedule_does_not_replace_a_saved_one(self):
        # The app removes the meals of a feeder when the feeder is removed.
        saved = {}
        migration.merge_saved(
            saved, migration.schedules([device("d1")], [meal("d1", "06:00")]), {}, "t1"
        )
        assert migration.merge_saved(saved, {"d1": []}, {}, "t2") is False
        assert [r["time"] for r in saved["d1"]["meals"]] == ["06:00"]


class TestMealsToRestore:
    def test_a_time_the_new_device_has_is_skipped(self):
        saved = [{"time": "06:00"}, {"time": "09:00"}]
        assert migration.meals_to_restore(saved, {"06:00"}) == [{"time": "09:00"}]

    def test_two_saved_meals_at_one_time_give_one_meal(self):
        saved = [{"time": "06:00", "name": "a"}, {"time": "06:00", "name": "b"}]
        assert migration.meals_to_restore(saved, set()) == [{"time": "06:00", "name": "a"}]


def test_describe_names_the_time_amount_and_state():
    text = migration.describe(
        [
            {"time": "06:00", "amount": 1, "name": "Meal", "enabled": True},
            {"time": "15:00", "amount": 2, "name": "", "enabled": False},
        ]
    )
    assert text == "- 06:00: 1x Meal\n- 15:00: 2x, off"
