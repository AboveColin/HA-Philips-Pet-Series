"""Constants for the Philips Pets Series integration."""

DOMAIN = "philips_pet_series"

WEEKDAYS = {
    0: "Monday",
    1: "Tuesday",
    2: "Wednesday",
    3: "Thursday",
    4: "Friday",
    5: "Saturday",
    6: "Sunday",
}

# Authentication config keys
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_ID_TOKEN = "id_token"
CONF_CALLBACK_URL = "callback_url"
CONF_CODE_VERIFIER = "code_verifier"
CONF_STATE = "state"
CONF_HOME_IDS = "home_ids"

# Regional config keys — chosen in the config flow, defaulted from HA's own
# config so they correspond to the user (nothing region-specific is hardcoded).
CONF_TIMEZONE = "timezone"
CONF_LANGUAGE = "language"
CONF_COUNTRY = "country"
CONF_CAMERA_MODE = "camera_mode"

# Datapoints once exposed as sensors that carried no usable meaning: 203 is a
# write-only command register, 204 and 206 are packed status/history integers
# with no published encoding, and 234/235 are audio-upload commands that always
# read back empty.  Listed here so their stale registry rows can be removed.
REMOVED_DP_SENSORS = ("203", "204", "206", "234", "235")

# ISO-3166 alpha-2 -> telephone dial code (for the country picker default).
COUNTRY_DIAL_CODES = {
    "US": "1", "CA": "1", "GB": "44", "IE": "353", "NL": "31", "BE": "32",
    "DE": "49", "FR": "33", "ES": "34", "IT": "39", "PT": "351", "CH": "41",
    "AT": "43", "DK": "45", "SE": "46", "NO": "47", "FI": "358", "PL": "48",
    "CZ": "420", "GR": "30", "LU": "352", "AU": "61", "NZ": "64", "JP": "81",
    "CN": "86", "IN": "91", "BR": "55", "MX": "52", "ZA": "27", "TR": "90",
}
