"""Options flow for Philips Pets Series integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol  # type: ignore[import-not-found]
from homeassistant import config_entries  # type: ignore[import-not-found]
from homeassistant.config_entries import ConfigEntry  # type: ignore[import-not-found]
from homeassistant.data_entry_flow import FlowResult  # type: ignore[import-not-found]

from .const import (
    CONF_TUYA_CLIENT_ID,
    CONF_TUYA_IP,
    CONF_TUYA_LOCAL_KEY,
)

_LOGGER = logging.getLogger(__name__)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle an options flow for Philips Pets Series."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            # Update options
            return self.async_create_entry(title="", data=user_input)

        # Get current values
        data = self.config_entry.data
        options = self.config_entry.options

        # Schema for Tuya configuration
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_TUYA_CLIENT_ID,
                    default=options.get(CONF_TUYA_CLIENT_ID)
                    or data.get(CONF_TUYA_CLIENT_ID)
                    or "",
                ): str,
                vol.Optional(
                    CONF_TUYA_IP,
                    default=options.get(CONF_TUYA_IP) or data.get(CONF_TUYA_IP) or "",
                ): str,
                vol.Optional(
                    CONF_TUYA_LOCAL_KEY,
                    default=options.get(CONF_TUYA_LOCAL_KEY)
                    or data.get(CONF_TUYA_LOCAL_KEY)
                    or "",
                ): str,
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            description_placeholders={
                "integration": "Philips Pet Series",
            },
        )
