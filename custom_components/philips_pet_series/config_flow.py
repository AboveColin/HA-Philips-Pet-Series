"""Config flow for Philips Pets Series integration."""

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
from petsseries.auth import AuthError, AuthManager  # type: ignore[import-not-found]

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_CALLBACK_URL,
    CONF_REFRESH_TOKEN,
    CONF_TUYA_CLIENT_ID,
    CONF_TUYA_IP,
    CONF_TUYA_LOCAL_KEY,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

# Schema for OAuth callback step
STEP_OAUTH_CALLBACK_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CALLBACK_URL): str,
    }
)

# Schema for manual token entry (fallback)
STEP_MANUAL_TOKEN_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCESS_TOKEN): str,
        vol.Required(CONF_REFRESH_TOKEN): str,
    }
)

# Schema for Tuya configuration (optional step)
STEP_TUYA_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_TUYA_CLIENT_ID): str,
        vol.Optional(CONF_TUYA_IP): str,
        vol.Optional(CONF_TUYA_LOCAL_KEY): str,
    }
)

# Legacy schema for full manual configuration
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


async def validate_tokens(
    hass: HomeAssistant, access_token: str, refresh_token: str
) -> Dict[str, Any]:
    """Validate access and refresh tokens by attempting to get user info."""
    client = PetsSeriesClient(
        token_file=None,
    )

    try:
        await client.auth.save_tokens(access_token, refresh_token)
        await client.initialize()
        user = await client.get_user_info()
        return {"title": f"Philips Pets Series ({user.name})"}
    except AuthError as err:
        raise InvalidAuth from err
    except Exception as err:
        _LOGGER.exception("Unexpected exception during token validation")
        raise CannotConnect from err
    finally:
        await client.close()


async def validate_input(hass: HomeAssistant, data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate the full user input (tokens + optional Tuya)."""
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
        token_file=None,
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
    """Handle a config flow for Philips Pets Series."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._auth_manager: Optional[AuthManager] = None
        self._authorization_url: Optional[str] = None
        self._code_verifier: Optional[str] = None
        self._state: Optional[str] = None
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._entry: Optional[config_entries.ConfigEntry] = None

    async def _get_auth_manager(self) -> AuthManager:
        """Get or create an AuthManager instance."""
        if self._auth_manager is None:
            self._auth_manager = AuthManager()
        return self._auth_manager

    async def _cleanup_auth_manager(self) -> None:
        """Clean up the AuthManager session."""
        if self._auth_manager:
            await self._auth_manager.close()
            self._auth_manager = None

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial step - show authentication options."""
        if user_input is not None:
            # User selected an authentication method
            auth_method = user_input.get("auth_method", "oauth")
            if auth_method == "oauth":
                return await self.async_step_oauth_start()
            else:
                return await self.async_step_manual()

        # Show auth method selection
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("auth_method", default="oauth"): vol.In(
                        {
                            "oauth": "Login with Philips (Recommended)",
                            "manual": "Enter tokens manually",
                        }
                    ),
                }
            ),
            description_placeholders={
                "title": "Choose Authentication Method",
            },
        )

    async def async_step_oauth_start(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Start the OAuth flow - generate authorization URL."""
        errors = {}

        try:
            auth_manager = await self._get_auth_manager()
            auth_data = await auth_manager.get_authorization_url()

            self._authorization_url = auth_data["authorization_url"]
            self._code_verifier = auth_data["code_verifier"]
            self._state = auth_data["state"]

            _LOGGER.debug("Generated authorization URL for OAuth flow")

            return await self.async_step_oauth_callback()

        except AuthError as err:
            _LOGGER.error("Failed to generate authorization URL: %s", err)
            errors["base"] = "auth_url_failed"
            return self.async_show_form(
                step_id="user",
                errors=errors,
                description_placeholders={
                    "error": str(err),
                },
            )

    async def async_step_oauth_callback(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the OAuth callback - user pastes the redirect URL."""
        errors = {}

        if user_input is not None:
            callback_url = user_input.get(CONF_CALLBACK_URL, "").strip()

            try:
                auth_manager = await self._get_auth_manager()

                # Parse the callback URL
                callback_data = AuthManager.parse_callback_url(callback_url)
                authorization_code = callback_data["code"]
                returned_state = callback_data.get("state")

                # Validate state if we have one
                if self._state and returned_state != self._state:
                    _LOGGER.warning(
                        "State mismatch: expected %s, got %s",
                        self._state,
                        returned_state,
                    )
                    # Continue anyway, some implementations may not preserve state

                # Exchange the code for tokens
                tokens = await auth_manager.exchange_authorization_code(
                    authorization_code=authorization_code,
                    code_verifier=self._code_verifier,
                )

                self._access_token = tokens.get("access_token")
                self._refresh_token = tokens.get("refresh_token")

                if not self._access_token or not self._refresh_token:
                    raise AuthError("Missing access_token or refresh_token in response")

                # Validate the tokens work
                await validate_tokens(
                    self.hass, self._access_token, self._refresh_token
                )

                # Proceed to optional Tuya configuration
                return await self.async_step_tuya()

            except AuthError as err:
                _LOGGER.error("OAuth callback failed: %s", err)
                errors["base"] = "invalid_auth"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception as err:
                _LOGGER.exception("Unexpected error during OAuth callback: %s", err)
                errors["base"] = "unknown"

        # Show the form to paste the callback URL
        return self.async_show_form(
            step_id="oauth_callback",
            data_schema=STEP_OAUTH_CALLBACK_SCHEMA,
            errors=errors,
            description_placeholders={
                "authorization_url": self._authorization_url or "",
            },
        )

    async def async_step_tuya(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle optional Tuya configuration."""
        errors = {}

        if user_input is not None:
            # Build the final data
            data = {
                CONF_ACCESS_TOKEN: self._access_token,
                CONF_REFRESH_TOKEN: self._refresh_token,
            }

            # Add Tuya credentials if provided
            if user_input.get(CONF_TUYA_CLIENT_ID):
                data[CONF_TUYA_CLIENT_ID] = user_input[CONF_TUYA_CLIENT_ID]
            if user_input.get(CONF_TUYA_IP):
                data[CONF_TUYA_IP] = user_input[CONF_TUYA_IP]
            if user_input.get(CONF_TUYA_LOCAL_KEY):
                data[CONF_TUYA_LOCAL_KEY] = user_input[CONF_TUYA_LOCAL_KEY]

            try:
                info = await validate_input(self.hass, data)
                await self._cleanup_auth_manager()
                return self.async_create_entry(title=info["title"], data=data)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except InvalidTuyaSupport:
                errors["base"] = "invalid_tuya_support"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="tuya",
            data_schema=STEP_TUYA_SCHEMA,
            errors=errors,
            description_placeholders={},
        )

    async def async_step_manual(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle manual token entry (fallback method)."""
        errors = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
                await self._cleanup_auth_manager()
                return self.async_create_entry(title=info["title"], data=user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except InvalidTuyaSupport:
                errors["base"] = "invalid_tuya_support"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="manual",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "login_url": "https://www.home.id/find-appliance"
            },
        )

    async def async_step_reauth(self, flow_input: dict) -> FlowResult:
        """Handle re-authentication."""
        entry_id = self.context.get("entry_id")
        if not entry_id:
            return self.async_abort(reason="unknown_entry")

        entry = self.hass.config_entries.async_get_entry(entry_id)
        if not entry:
            return self.async_abort(reason="unknown_entry")

        self._entry = entry

        _LOGGER.debug("Starting reauthentication flow for entry_id: %s", entry_id)
        return await self.async_step_reauth_method()

    async def async_step_reauth_method(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Choose re-authentication method."""
        if user_input is not None:
            auth_method = user_input.get("auth_method", "oauth")
            if auth_method == "oauth":
                return await self.async_step_reauth_oauth_start()
            else:
                return await self.async_step_reauth_confirm()

        return self.async_show_form(
            step_id="reauth_method",
            data_schema=vol.Schema(
                {
                    vol.Required("auth_method", default="oauth"): vol.In(
                        {
                            "oauth": "Login with Philips (Recommended)",
                            "manual": "Enter tokens manually",
                        }
                    ),
                }
            ),
            description_placeholders={},
        )

    async def async_step_reauth_oauth_start(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Start OAuth flow for re-authentication."""
        try:
            auth_manager = await self._get_auth_manager()
            auth_data = await auth_manager.get_authorization_url()

            self._authorization_url = auth_data["authorization_url"]
            self._code_verifier = auth_data["code_verifier"]
            self._state = auth_data["state"]

            return await self.async_step_reauth_oauth_callback()

        except AuthError as err:
            _LOGGER.error("Failed to generate authorization URL: %s", err)
            return await self.async_step_reauth_confirm()

    async def async_step_reauth_oauth_callback(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle OAuth callback for re-authentication."""
        errors = {}

        if user_input is not None:
            callback_url = user_input.get(CONF_CALLBACK_URL, "").strip()

            try:
                auth_manager = await self._get_auth_manager()
                callback_data = AuthManager.parse_callback_url(callback_url)
                authorization_code = callback_data["code"]

                tokens = await auth_manager.exchange_authorization_code(
                    authorization_code=authorization_code,
                    code_verifier=self._code_verifier,
                )

                access_token = tokens.get("access_token")
                refresh_token = tokens.get("refresh_token")

                if not access_token or not refresh_token:
                    raise AuthError("Missing tokens in response")

                # Validate tokens
                await validate_tokens(self.hass, access_token, refresh_token)

                # Update the existing entry using the helper method
                if self._entry is None:
                    errors["base"] = "unknown_entry"
                    return self.async_show_form(
                        step_id="reauth_oauth_callback",
                        data_schema=STEP_OAUTH_CALLBACK_SCHEMA,
                        errors=errors,
                        description_placeholders={
                            "authorization_url": self._authorization_url or "",
                        },
                    )

                await self._cleanup_auth_manager()
                return self.async_update_reload_and_abort(
                    self._entry,
                    data={
                        **self._entry.data,
                        CONF_ACCESS_TOKEN: access_token,
                        CONF_REFRESH_TOKEN: refresh_token,
                    },
                )

            except (AuthError, InvalidAuth):
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception as err:
                _LOGGER.exception("Unexpected error: %s", err)
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="reauth_oauth_callback",
            data_schema=STEP_OAUTH_CALLBACK_SCHEMA,
            errors=errors,
            description_placeholders={
                "authorization_url": self._authorization_url or "",
            },
        )

    async def async_step_reauth_confirm(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle manual re-authentication confirmation."""
        if user_input is None:
            return self.async_show_form(
                step_id="reauth_confirm",
                description_placeholders={
                    "login_url": "https://www.home.id/find-appliance"
                },
                data_schema=STEP_REAUTH_DATA_SCHEMA,
            )

        errors = {}

        if self._entry is None:
            errors["base"] = "unknown_entry"
            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=STEP_REAUTH_DATA_SCHEMA,
                errors=errors,
                description_placeholders={
                    "login_url": "https://www.home.id/find-appliance"
                },
            )

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
        except Exception:
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            await self._cleanup_auth_manager()
            return self.async_update_reload_and_abort(
                self._entry,
                data=updated_data,
            )

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
        """Handle reconfiguration."""
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
        except Exception:
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            entry_id = self.context.get("entry_id")
            if not entry_id:
                return self.async_abort(reason="unknown_entry")

            entry = self.hass.config_entries.async_get_entry(entry_id)
            if not entry:
                return self.async_abort(reason="unknown_entry")

            self.hass.config_entries.async_update_entry(entry, data=user_input)
            return self.async_abort(reason="reconfigure_successful")

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "login_url": "https://www.home.id/find-appliance"
            },
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""

    def __init__(self, message: str = "Cannot connect") -> None:
        super().__init__(message)


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""

    def __init__(self, message: str = "Invalid auth") -> None:
        super().__init__(message)


class InvalidTuyaSupport(HomeAssistantError):
    """Error to indicate Tuya support is invalid."""

    def __init__(self, message: str = "Invalid Tuya support") -> None:
        super().__init__(message)
