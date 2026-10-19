"""Tests for the camera bridge's MQTT settings.

A camera set up in the Philips HomeID app lives in HomeID's Tuya app, not in the
Pet Series app's. The settings must be signed as the app that holds the camera:
its partner id starts the username, its app id is inside it, and its package
starts the client id. A camera signed as the wrong app gets no signaling.
"""

import asyncio
import importlib.util
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
from tuya_mobile import PurePythonTuyaSigner

# Loaded straight from the file, as in test_firmware.py: importing the package
# runs its __init__, which needs Home Assistant.
_MODULE = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "philips_pet_series"
    / "camera_mqtt.py"
)
_spec = importlib.util.spec_from_file_location("pps_camera_mqtt", _MODULE)
camera_mqtt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(camera_mqtt)

# The two apps' public Tuya application values, as in petsseries.backends.
PET_SERIES_APP = {
    "app_id": "7gqdt8hrgamaxeksxchg",
    "app_secret": "55v8jwqadnkpmdxtr4ep9yxefm7csgr7",
    "cert_sha256_hex": "1c625cd6777b18be9486130956c227b18aefcce5decc9505d46302ad71c806c5",
    "app_key": "fxe8mk3xnn4tjna35gqmvjd4kwvw3dyq",
    "package": "com.versuni.nbx.petsseries",
}
HOMEID_APP = {
    "app_id": "d997esphw5fevawrcyud",
    "app_secret": "fcxp5hwguv5vpa4wveu8tujnhky8nhde",
    "cert_sha256_hex": "d2d695a11d1b84f925a9456e27f445e9fd87c37463aa8a3432a66a233b0fd50f",
    "app_key": "dgsgxpwew54gdpcm5cuqfrvjpakxgvmn",
    "package": "com.philips.ka.oneka.app",
}


@dataclass
class FakeSession:
    """The fields of petsseries.tuya_app.TuyaSession that the bridge reads."""

    client: object
    backend: object
    partner_id: str


def session(app, partner_id, *, mobile_url="https://a1.tuyaeu.com/api.json", **fields):
    client = SimpleNamespace(
        signer=PurePythonTuyaSigner(**app),
        uid=fields.get("uid", "eu1700000000000abcd"),
        sid=fields.get("sid", "eu1700000000000abcdsid"),
        ecode=fields.get("ecode", "ecode0123456789"),
        mobile_url=mobile_url,
    )
    return FakeSession(client, SimpleNamespace(package=app["package"]), partner_id)


def settings(tuya, device_id="dev1"):
    return asyncio.run(camera_mqtt.mqtt_settings(tuya, device_id))


class TestEachAppSignsItsOwnCamera:
    def test_a_pet_series_camera_signs_as_the_pet_series_app(self):
        mqtt = settings(session(PET_SERIES_APP, "p2065237"))
        assert mqtt["username"].startswith("p2065237_v1_7gqdt8hrgamaxeksxchg_")
        assert mqtt["client_id"].startswith("com.versuni.nbx.petsseries_mb_")

    def test_a_homeid_camera_signs_as_the_homeid_app(self):
        mqtt = settings(session(HOMEID_APP, "p2645382"))
        assert mqtt["username"].startswith("p2645382_v1_d997esphw5fevawrcyud_")
        assert mqtt["client_id"].startswith("com.philips.ka.oneka.app_mb_")

    def test_the_two_apps_derive_different_passwords_from_one_ecode(self):
        pet = settings(session(PET_SERIES_APP, "p2065237"))
        homeid = settings(session(HOMEID_APP, "p2645382"))
        assert pet["password"] != homeid["password"]

    def test_the_topics_are_the_cameras_and_the_uid_is_the_sessions(self):
        mqtt = settings(session(HOMEID_APP, "p2645382", uid="eu1uid"), "camera42")
        assert mqtt["publish_topic"] == "smart/mb/out/camera42"
        assert mqtt["subscribe_topic"] == "smart/mb/in/camera42"
        assert mqtt["uid"] == "eu1uid"


class TestSessionChecks:
    @pytest.mark.parametrize("missing", ["uid", "sid", "ecode"])
    def test_a_session_without_mqtt_fields_is_refused(self, missing):
        with pytest.raises(RuntimeError, match="no MQTT fields"):
            settings(session(HOMEID_APP, "p2645382", **{missing: ""}))

    def test_a_session_without_a_client_is_refused(self):
        with pytest.raises(RuntimeError, match="no MQTT fields"):
            settings(FakeSession(None, SimpleNamespace(package="x"), "p1"))


class TestBroker:
    @pytest.mark.parametrize(
        ("mobile_url", "broker"),
        [
            ("https://a1.tuyaeu.com/api.json", "ssl://m1.tuyaeu.com:8883"),
            ("https://a1.tuyaus.com/api.json", "ssl://m1.tuyaus.com:8883"),
            ("", "ssl://m1.tuyaeu.com:8883"),
            ("not a url", "ssl://m1.tuyaeu.com:8883"),
        ],
    )
    def test_the_broker_follows_the_sessions_region(self, mobile_url, broker):
        mqtt = settings(session(HOMEID_APP, "p2645382", mobile_url=mobile_url))
        assert mqtt["broker"] == broker
