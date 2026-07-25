from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import List, override

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import homeassistant.util.dt as dt_util

from . import DOMAIN, PhilipsPetsSeriesDataUpdateCoordinator
from .entity import iter_home_devices
from .meals import occurrences as meal_occurrences

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Philips Pets Series calendar entities."""
    coordinator: PhilipsPetsSeriesDataUpdateCoordinator = (
        hass.data[DOMAIN][config_entry.entry_id]["coordinator"])
    client = hass.data[DOMAIN][config_entry.entry_id]["client"]

    calendars = []

    for home, device in iter_home_devices(coordinator):
            # Create a calendar entity for each device
            calendars.append(PhilipsPetsSeriesCalendar(coordinator, client, home, device))

    async_add_entities(calendars)

class PhilipsPetsSeriesCalendar(CalendarEntity):
    """Representation of a Philips Pets Series meal calendar."""

    def __init__(self, coordinator, client, home, device):
        """Initialize the calendar entity."""
        self.coordinator = coordinator
        self.client = client
        self.home = home
        self.device = device
        # "Meal schedule" rather than "Meals": a calendar only reads "on" while a
        # meal is being served, and "Meals: Off" looks like feeding is disabled.
        self._attr_name = "Meal schedule"
        self._attr_unique_id = f"{device.id}_meal_calendar"
        self._attr_timezone = str(self.coordinator.hass.config.time_zone)
        self._events: List[CalendarEvent] = []

        _LOGGER.debug(f"Initialized calendar for device {device.id}")

    @property
    def device_info(self):
        """Return device information.

        Only the identifier is claimed here: publishing a second, hardcoded
        model for the same device made the registry entry flip-flop depending
        on which platform loaded last.
        """
        return {"identifiers": {(DOMAIN, self.device.id)}}

    async def async_get_events(
        self, hass, start_date: datetime, end_date: datetime
    ) -> List[CalendarEvent]:
        """Return a list of CalendarEvent based on Meal data within the given date range."""
        events = self._build_events(start_date, end_date)
        self._events = events
        _LOGGER.debug("Generated %s events for device %s", len(events), self.device.id)
        return events

    def _build_events(
        self, start_date: datetime, end_date: datetime
    ) -> List[CalendarEvent]:
        """Expand this device's enabled meals into events across a date range."""
        return [
            CalendarEvent(
                summary=f"{occurrence.name} (Portion: {occurrence.portions})",
                start=occurrence.start,
                end=occurrence.end,
                description=(
                    f"Feed {occurrence.portions} portions at {occurrence.feed_time}"
                ),
                location=self.home.name,
            )
            for occurrence in meal_occurrences(
                self.coordinator, self.device.id, start_date, end_date
            )
        ]

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming meal.

        Computed straight from the coordinator's meal schedule: relying on the
        cache filled by ``async_get_events`` left this permanently empty until
        somebody opened the calendar panel, so "next meal" automations never
        fired on a fresh install.
        """
        now = dt_util.now()
        for event in self._build_events(now, now + timedelta(days=8)):
            if event.end >= now:
                return event
        return None

    @property
    def available(self) -> bool:
        """Follow the coordinator so total API failure is visible."""
        return self.coordinator.last_update_success
