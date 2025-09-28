from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import voluptuous as vol  # type: ignore[import-not-found]
from homeassistant import config_entries  # type: ignore[import-not-found]
from homeassistant.core import HomeAssistant  # type: ignore[import-not-found]
from homeassistant.data_entry_flow import FlowResult  # type: ignore[import-not-found]
from homeassistant.exceptions import (
    HomeAssistantError,  # type: ignore[import-not-found]
)
from petsseries.api import PetsSeriesClient  # type: ignore[import-not-found]

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_TUYA_CLIENT_ID,
    CONF_TUYA_IP,
    CONF_TUYA_LOCAL_KEY,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCESS_TOKEN): str,
        vol.Required(CONF_REFRESH_TOKEN): str,
        vol.Optional(CONF_TUYA_CLIENT_ID): str,
        vol.Optional(CONF_TUYA_IP): str,
        vol.Optional(CONF_TUYA_LOCAL_KEY): str,
    }
)

STEP_REAUTH_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCESS_TOKEN): str,
        vol.Required(CONF_REFRESH_TOKEN): str,
    }
)


async def validate_input(hass: HomeAssistant, data: Dict[str, Any]) -> Dict[str, Any]:
    from petsseries.auth import AuthError  # type: ignore[import-not-found]

    access_token = data[CONF_ACCESS_TOKEN]
    refresh_token = data[CONF_REFRESH_TOKEN]
    tuya_credentials = None

    if all(
        key in data and data[key]
        for key in (CONF_TUYA_CLIENT_ID, CONF_TUYA_IP, CONF_TUYA_LOCAL_KEY)
    ):
        tuya_credentials = {
            "client_id": data[CONF_TUYA_CLIENT_ID],
            "ip": data[CONF_TUYA_IP],
            "local_key": data[CONF_TUYA_LOCAL_KEY],
            "version": data.get("tuya_version", 3.4),
        }

    client = PetsSeriesClient(
        token_file="tokens.json",
        tuya_credentials=tuya_credentials,
    )

    try:
        await client.auth.save_tokens(access_token, refresh_token)
        await client.initialize()
        user = await client.get_user_info()
    except AuthError as err:
        raise InvalidAuth from err
    except ImportError as err:
        _LOGGER.error("Tuya support requested but not available: %s", err)
        raise InvalidTuyaSupport from err
    except Exception as err:
        _LOGGER.exception("Unexpected exception")
        raise CannotConnect from err
    finally:
        await client.close()

    return {"title": f"Philips Pets Series ({user.name})"}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    VERSION = 2
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_DATA_SCHEMA,
                description_placeholders={
                    "login_url": "https://www.home.id/find-appliance"
                },
            )

        errors = {}

        try:
            info = await validate_input(self.hass, user_input)
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except InvalidTuyaSupport:
            errors["base"] = "invalid_tuya_support"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "login_url": "https://www.home.id/find-appliance"
            },
        )

    async def async_step_reauth(self, flow_input: dict) -> FlowResult:
        entry_id = self.context.get("entry_id")
        if not entry_id:
            return self.async_abort(reason="unknown_entry")

        entry = self.hass.config_entries.async_get_entry(entry_id)
        if not entry:
            return self.async_abort(reason="unknown_entry")

        self._entry = entry

        _LOGGER.debug("Starting reauthentication flow for entry_id: %s", entry_id)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the re-authentication confirmation and collect new credentials."""
        if user_input is None:
            return self.async_show_form(
                step_id="reauth_confirm",
                description_placeholders={
                    "login_url": "https://www.home.id/find-appliance"
                },
                data_schema=STEP_REAUTH_DATA_SCHEMA,
            )

        errors = {}

        updated_data = self._entry.data.copy()
        updated_data[CONF_ACCESS_TOKEN] = user_input[CONF_ACCESS_TOKEN]
        updated_data[CONF_REFRESH_TOKEN] = user_input[CONF_REFRESH_TOKEN]

        try:
            await validate_input(self.hass, updated_data)
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except InvalidTuyaSupport:
            errors["base"] = "invalid_tuya_support"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            self.hass.config_entries.async_update_entry(self._entry, data=updated_data)
            return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "login_url": "https://www.home.id/find-appliance"
            },
        )

    async def async_step_reconfigure(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        if user_input is None:
            return self.async_show_form(
                step_id="reconfigure",
                data_schema=STEP_USER_DATA_SCHEMA,
                description_placeholders={
                    "login_url": "https://www.home.id/find-appliance"
                },
            )

        errors = {}

        try:
            await validate_input(self.hass, user_input)
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except InvalidTuyaSupport:
            errors["base"] = "invalid_tuya_support"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            # Update existing entry instead of creating a new one
            entry_id = self.context.get("entry_id")
            if not entry_id:
                return self.async_abort(reason="unknown_entry")

            entry = self.hass.config_entries.async_get_entry(entry_id)
            if not entry:
                return self.async_abort(reason="unknown_entry")

            self.hass.config_entries.async_update_entry(entry, data=user_input)
            return self.async_abort(reason="reconfigure_successful")

        # If we reach here, show the form again with validation errors
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "login_url": "https://www.home.id/find-appliance"
            },
        )


class CannotConnect(HomeAssistantError):
    def __init__(self, message: str = "Cannot connect") -> None:
        super().__init__(message)


class InvalidAuth(HomeAssistantError):
    def __init__(self, message: str = "Invalid auth") -> None:
        super().__init__(message)


class InvalidTuyaSupport(HomeAssistantError):
    def __init__(self, message: str = "Invalid Tuya support") -> None:
        super().__init__(message)
