"""Email OTP config flow for Philips Pets Series."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import voluptuous as vol  # type: ignore[import-not-found]
from homeassistant import config_entries  # type: ignore[import-not-found]
from homeassistant.data_entry_flow import FlowResult  # type: ignore[import-not-found]
from homeassistant.exceptions import HomeAssistantError  # type: ignore[import-not-found]
from petsseries.api import PetsSeriesClient  # type: ignore[import-not-found]
from petsseries.auth import AuthError, AuthManager  # type: ignore[import-not-found]

from homeassistant.helpers import selector  # type: ignore[import-not-found]
from zoneinfo import available_timezones

from .bridge import (
    CAMERA_MODE_ON_DEMAND,
    CAMERA_MODES,
    IDLE_TIMEOUT,
    IDLE_TIMEOUT_MAX_MINUTES,
    IDLE_TIMEOUT_MIN_MINUTES,
)
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_CAMERA_MODE,
    CONF_COUNTRY,
    CONF_IDLE_TIMEOUT,
    CONF_HOME_IDS,
    CONF_ID_TOKEN,
    CONF_LANGUAGE,
    CONF_REFRESH_TOKEN,
    CONF_TIMEZONE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

ISSUE_URL = "https://github.com/AboveColin/HA-Philips-Pet-Series/issues"


def _describe(err: BaseException) -> str:
    """Name the failure the way a bug report needs it.

    Reports the cause when there is one, because every error the user can see
    here is a wrapper: CannotConnect and InvalidAuth carry the real exception
    in __cause__, and the wrapper's own name says nothing.
    """
    cause = err.__cause__ or err
    text = str(cause).strip()
    described = f"{type(cause).__name__}: {text}" if text else type(cause).__name__
    # The longest of these measured across the known failures is 68 characters,
    # but an exception is free to carry a whole HTTP body, and this string goes
    # into a dialog box. 500 is a tripwire, not a budget: nothing legitimate here
    # comes close.
    return described if len(described) <= 500 else described[:499] + "\u2026"


class CannotConnect(HomeAssistantError):
    """The service could not be reached."""


class InvalidAuth(HomeAssistantError):
    """The email code or returned credentials were invalid."""


class NoHomes(HomeAssistantError):
    """The login worked, but the Philips account owns no home.

    Kept apart from CannotConnect because the two need opposite actions from
    the user: one is a network to check, this one is a home to create in the
    Philips app. Reporting it as CannotConnect sends people to debug a working
    network.
    """


async def _validate_tokens(access_token: str, refresh_token: str, id_token: str | None = None) -> str:
    """Validate credentials and return a stable entry title."""
    client = PetsSeriesClient(
        token_file=None,
        access_token=access_token,
        refresh_token=refresh_token,
    )
    try:
        await client.initialize()
        user = await client.get_user_info()
        return f"Philips Pets Series ({user.name or user.email or user.sub})"
    except AuthError as err:
        _LOGGER.exception("Philips rejected the credentials just issued")
        raise InvalidAuth from err
    except Exception as err:
        # Everything non-auth becomes one opaque "cannot connect" for the user,
        # so without this line the actual cause never reaches the log and the
        # failure is unattributable from a bug report.
        _LOGGER.exception("Philips credential validation failed")
        raise CannotConnect from err
    finally:
        await client.close()


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    """Handle Philips login using an emailed one-time code."""

    VERSION = 4

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "OptionsFlowHandler":
        """Return the options flow for camera-streaming behaviour."""
        return OptionsFlowHandler()

    def __init__(self) -> None:
        self._auth: Optional[AuthManager] = None
        self._email = ""
        self._vtoken: Optional[str] = None
        self._entry_data: Optional[Dict[str, Any]] = None
        self._entry: Optional[config_entries.ConfigEntry] = None
        self._detail = ""
        self._detail_is_bug = True

    def _set_detail(self, text: str, *, is_bug: bool = True) -> None:
        """Record what to show with the form, and whether it is worth reporting.

        A missing home is the user's to fix in the Philips app, so pointing them
        at the issue tracker for it would only generate noise.
        """
        self._detail = text
        self._detail_is_bug = is_bug

    def _placeholders(self) -> Dict[str, str]:
        """Form placeholders, carrying the last failure into the dialog.

        The error line itself renders as plain text, so the code block and the
        issue link have to travel in the step description, which Home Assistant
        renders as markdown.
        """
        if not self._detail:
            return {"email": self._email, "detail": ""}
        report = (
            f"\n\nReport this at {ISSUE_URL} with the lines above."
            if self._detail_is_bug
            else ""
        )
        return {
            "email": self._email,
            "detail": f"\n\n**Details**\n\n```\n{self._detail}\n```{report}",
        }

    async def _get_auth(self) -> AuthManager:
        if self._auth is None:
            self._auth = AuthManager(token_file=None)
        return self._auth

    async def _close_auth(self) -> None:
        if self._auth is not None:
            await self._auth.close()
            self._auth = None

    async def async_remove(self) -> None:
        """Close the login session when the flow ends.

        Every _close_auth call sits on a success path, so a flow abandoned after
        a failed code leaked its aiohttp session and logged "Unclosed client
        session" instead of anything about the failure.
        """
        await self._close_auth()

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Collect the account email and send its one-time code."""
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")
        errors: Dict[str, str] = {}
        if user_input is not None:
            self._set_detail("")
            self._email = user_input["email"].strip().lower()
            try:
                response = await (await self._get_auth()).request_email_code(self._email)
                self._vtoken = response.get("vToken")
                return await self.async_step_code()
            except AuthError as err:
                _LOGGER.exception("Could not send Philips login code")
                self._set_detail(_describe(err))
                errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required("email"): str}),
            errors=errors,
            description_placeholders=self._placeholders(),
        )

    async def async_step_code(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Collect the emailed code and finish authentication."""
        errors: Dict[str, str] = {}
        if user_input is not None:
            self._set_detail("")
            try:
                tokens = await (await self._get_auth()).login_with_email_code(
                    self._email, user_input["code"], self._vtoken
                )
                access_token = tokens.get("access_token")
                refresh_token = tokens.get("refresh_token")
                if not access_token or not refresh_token:
                    raise InvalidAuth("Philips did not return usable tokens")
                await _validate_tokens(access_token, refresh_token, tokens.get("id_token"))
                client = PetsSeriesClient(token_file=None, access_token=access_token, refresh_token=refresh_token)
                await client.initialize()
                try:
                    homes = await client.get_homes()
                finally:
                    await client.close()
                if not homes:
                    raise NoHomes
                await self._close_auth()
                self._entry_data = {
                    CONF_ACCESS_TOKEN: access_token,
                    CONF_REFRESH_TOKEN: refresh_token,
                    CONF_ID_TOKEN: tokens.get("id_token"),
                    CONF_HOME_IDS: [str(home.id) for home in homes],
                }
                return await self.async_step_settings()
            except InvalidAuth as err:
                _LOGGER.exception("Philips login rejected the credentials")
                self._set_detail(_describe(err))
                errors["base"] = "invalid_auth"
            except AuthError as err:
                _LOGGER.exception("Philips OTP login failed")
                self._set_detail(_describe(err))
                errors["base"] = "invalid_auth"
            except NoHomes:
                # The form tells the user what to do. This line exists so the
                # cause is also in a log they paste into a bug report, where
                # the form text is not.
                _LOGGER.warning(
                    "Philips login for %s succeeded, but the account has no home",
                    self._email,
                )
                self._set_detail(
                    f"Signed in as {self._email}, "
                    "but GET /api/homes returned no homes for this account.",
                    is_bug=False,
                )
                errors["base"] = "no_homes"
            except CannotConnect as err:
                self._set_detail(_describe(err))
                errors["base"] = "cannot_connect"
            except Exception as err:
                _LOGGER.exception("Unexpected Philips OTP login failure")
                self._set_detail(_describe(err))
                errors["base"] = "unknown"
        return self.async_show_form(
            step_id="code",
            data_schema=vol.Schema({vol.Required("code"): str}),
            errors=errors,
            description_placeholders=self._placeholders(),
        )

    async def async_step_settings(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Collect regional settings and the camera mode.

        timezone / language / country are sent in the Tuya mobile-app requests so
        they match the account holder — nothing region-specific is hardcoded.

        The camera mode is asked here as well as in the options: the default
        suits most people, but anyone pointing an external recorder at the
        stream needs "always", and would otherwise have to discover that setting
        after their recording had already stopped working.
        """
        if user_input is not None:
            return self.async_create_entry(
                title=f"Philips Pets Series ({self._email})",
                data={**(self._entry_data or {}), **user_input},
            )
        tz_default = self.hass.config.time_zone or "UTC"
        lang_default = (self.hass.config.language or "en").split("-")[0]
        country_default = (self.hass.config.country or "").upper() or "US"
        schema = vol.Schema(
            {
                vol.Required(CONF_TIMEZONE, default=tz_default): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=sorted(available_timezones()),
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    )
                ),
                vol.Required(
                    CONF_LANGUAGE, default=lang_default
                ): selector.LanguageSelector(selector.LanguageSelectorConfig()),
                vol.Required(
                    CONF_COUNTRY, default=country_default
                ): selector.CountrySelector(selector.CountrySelectorConfig()),
                vol.Required(
                    CONF_CAMERA_MODE, default=CAMERA_MODE_ON_DEMAND
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=list(CAMERA_MODES),
                        translation_key="camera_mode",
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="settings", data_schema=schema)

    async def async_step_reconfigure(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Start reconfiguration with the email OTP flow."""
        entry_id = self.context.get("entry_id")
        self._entry = self.hass.config_entries.async_get_entry(entry_id) if entry_id else None
        if self._entry is None:
            return self.async_abort(reason="unknown_entry")
        errors: Dict[str, str] = {}
        if user_input is not None:
            self._set_detail("")
            self._email = user_input["email"].strip().lower()
            try:
                response = await (await self._get_auth()).request_email_code(self._email)
                self._vtoken = response.get("vToken")
                return await self.async_step_reconfigure_code()
            except AuthError as err:
                _LOGGER.exception("Could not send Philips reconfiguration code")
                self._set_detail(_describe(err))
                errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({vol.Required("email"): str}),
            errors=errors,
            description_placeholders=self._placeholders(),
        )

    async def async_step_reconfigure_code(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Validate the OTP and replace credentials on the existing entry."""
        errors: Dict[str, str] = {}
        if user_input is not None and self._entry is not None:
            self._set_detail("")
            try:
                tokens = await (await self._get_auth()).login_with_email_code(
                    self._email, user_input["code"], self._vtoken
                )
                access_token = tokens.get("access_token")
                refresh_token = tokens.get("refresh_token")
                if not access_token or not refresh_token:
                    raise InvalidAuth("Philips did not return usable tokens")
                await _validate_tokens(access_token, refresh_token, tokens.get("id_token"))
                client = PetsSeriesClient(token_file=None, access_token=access_token, refresh_token=refresh_token)
                await client.initialize()
                try:
                    homes = await client.get_homes()
                finally:
                    await client.close()
                if not homes:
                    raise NoHomes
                await self._close_auth()
                return self.async_update_reload_and_abort(
                    self._entry,
                    data={
                        **self._entry.data,
                        CONF_ACCESS_TOKEN: access_token,
                        CONF_REFRESH_TOKEN: refresh_token,
                        CONF_ID_TOKEN: tokens.get("id_token"),
                        CONF_HOME_IDS: [str(home.id) for home in homes],
                    },
                )
            except InvalidAuth as err:
                _LOGGER.exception("Philips login rejected the credentials")
                self._set_detail(_describe(err))
                errors["base"] = "invalid_auth"
            except AuthError as err:
                _LOGGER.exception("Philips OTP login failed")
                self._set_detail(_describe(err))
                errors["base"] = "invalid_auth"
            except NoHomes:
                # The form tells the user what to do. This line exists so the
                # cause is also in a log they paste into a bug report, where
                # the form text is not.
                _LOGGER.warning(
                    "Philips login for %s succeeded, but the account has no home",
                    self._email,
                )
                self._set_detail(
                    f"Signed in as {self._email}, "
                    "but GET /api/homes returned no homes for this account.",
                    is_bug=False,
                )
                errors["base"] = "no_homes"
            except CannotConnect as err:
                self._set_detail(_describe(err))
                errors["base"] = "cannot_connect"
            except Exception as err:
                _LOGGER.exception("Unexpected Philips reconfiguration failure")
                self._set_detail(_describe(err))
                errors["base"] = "unknown"
        return self.async_show_form(
            step_id="reconfigure_code",
            data_schema=vol.Schema({vol.Required("code"): str}),
            errors=errors,
            description_placeholders=self._placeholders(),
        )

    async def async_step_reauth(self, flow_input: dict) -> FlowResult:
        """Re-authenticate an existing entry with the same email OTP flow."""
        entry_id = self.context.get("entry_id")
        self._entry = self.hass.config_entries.async_get_entry(entry_id) if entry_id else None
        if self._entry is None:
            return self.async_abort(reason="unknown_entry")
        return await self.async_step_reauth_user()

    async def async_step_reauth_user(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Collect the re-authentication email."""
        errors: Dict[str, str] = {}
        if user_input is not None:
            self._set_detail("")
            self._email = user_input["email"].strip().lower()
            try:
                response = await (await self._get_auth()).request_email_code(self._email)
                self._vtoken = response.get("vToken")
                return await self.async_step_reauth_code()
            except AuthError as err:
                _LOGGER.exception("Could not send Philips re-authentication code")
                self._set_detail(_describe(err))
                errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="reauth_user",
            data_schema=vol.Schema({vol.Required("email"): str}),
            errors=errors,
            description_placeholders=self._placeholders(),
        )

    async def async_step_reauth_code(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Apply refreshed tokens to the existing entry."""
        errors: Dict[str, str] = {}
        if user_input is not None and self._entry is not None:
            self._set_detail("")
            try:
                tokens = await (await self._get_auth()).login_with_email_code(
                    self._email, user_input["code"], self._vtoken
                )
                access_token = tokens.get("access_token")
                refresh_token = tokens.get("refresh_token")
                if not access_token or not refresh_token:
                    raise InvalidAuth
                await _validate_tokens(access_token, refresh_token, tokens.get("id_token"))
                await self._close_auth()
                return self.async_update_reload_and_abort(
                    self._entry,
                    data={
                        **self._entry.data,
                        CONF_ACCESS_TOKEN: access_token,
                        CONF_REFRESH_TOKEN: refresh_token,
                        CONF_ID_TOKEN: tokens.get("id_token"),
                    },
                )
            except InvalidAuth as err:
                _LOGGER.exception("Philips login rejected the credentials")
                self._set_detail(_describe(err))
                errors["base"] = "invalid_auth"
            except AuthError as err:
                _LOGGER.exception("Philips OTP login failed")
                self._set_detail(_describe(err))
                errors["base"] = "invalid_auth"
            except CannotConnect as err:
                self._set_detail(_describe(err))
                errors["base"] = "cannot_connect"
            except Exception as err:
                _LOGGER.exception("Unexpected Philips re-authentication failure")
                self._set_detail(_describe(err))
                errors["base"] = "unknown"
        return self.async_show_form(
            step_id="reauth_code",
            data_schema=vol.Schema({vol.Required("code"): str}),
            errors=errors,
            description_placeholders=self._placeholders(),
        )


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Adjust behaviour that does not require re-authentication."""

    async def async_step_init(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        current = {**self.config_entry.data, **self.config_entry.options}.get(
            CONF_CAMERA_MODE, CAMERA_MODE_ON_DEMAND
        )
        if current not in CAMERA_MODES:
            current = CAMERA_MODE_ON_DEMAND
        merged = {**self.config_entry.data, **self.config_entry.options}
        idle_default = merged.get(
            CONF_IDLE_TIMEOUT, int(IDLE_TIMEOUT.total_seconds() // 60)
        )
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_CAMERA_MODE, default=current
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=list(CAMERA_MODES),
                        translation_key="camera_mode",
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_IDLE_TIMEOUT, default=idle_default
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=IDLE_TIMEOUT_MIN_MINUTES,
                        max=IDLE_TIMEOUT_MAX_MINUTES,
                        step=1,
                        unit_of_measurement="min",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
