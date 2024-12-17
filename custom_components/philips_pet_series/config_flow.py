from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.data_entry_flow import FlowResult

from petsseries import PetsSeriesClient
from petsseries.auth import AuthError

from .const import (
    DOMAIN,
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_TUYA_CLIENT_ID,
    CONF_TUYA_IP,
    CONF_TUYA_LOCAL_KEY,
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
    """Validate the user input allows us to connect."""

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
        access_token=access_token,
        refresh_token=refresh_token,
        tuya_credentials=tuya_credentials,
    )

    try:
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


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Philips Pets Series."""

    VERSION = 2
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial step."""
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

    async def async_step_reauth(self, entry_data: Dict[str, Any]) -> FlowResult:
        """Handle configuration reauthentication."""
        self._entry = entry_data
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the re-authentication confirmation."""
        if user_input is None:
            return self.async_show_form(
                step_id="reauth_confirm",
                description_placeholders={
                    "login_url": "https://www.home.id/find-appliance"
                },
                data_schema=vol.Schema({}),
            )

        return await self.async_step_reauth_update()

    async def async_step_reauth_update(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Prompt the user to re-enter credentials during re-authentication."""
        if user_input is None:
            return self.async_show_form(
                step_id="reauth_update",
                data_schema=STEP_REAUTH_DATA_SCHEMA,
                description_placeholders={
                    "login_url": "https://www.home.id/find-appliance"
                },
            )

        errors = {}

        updated_data = self._entry.copy()
        updated_data[CONF_ACCESS_TOKEN] = user_input[CONF_ACCESS_TOKEN]
        updated_data[CONF_REFRESH_TOKEN] = user_input[CONF_REFRESH_TOKEN]

        try:
            info = await validate_input(self.hass, updated_data)
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
            self.hass.config_entries.async_update_entry(
                self._entry, data=updated_data
            )
            return self.async_create_entry(title=info["title"], data=updated_data)

        return self.async_show_form(
            step_id="reauth_update",
            data_schema=STEP_REAUTH_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "login_url": "https://www.home.id/find-appliance"
            },
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""

    def __init__(self, message: str = "Cannot connect") -> None:
        """Initialize the error."""
        super().__init__(message)


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""

    def __init__(self, message: str = "Invalid auth") -> None:
        """Initialize the error."""
        super().__init__(message)


class InvalidTuyaSupport(HomeAssistantError):
    """Error to indicate Tuya support is invalid or dependencies are missing."""

    def __init__(self, message: str = "Invalid Tuya support") -> None:
        """Initialize the error."""
        super().__init__(message)
