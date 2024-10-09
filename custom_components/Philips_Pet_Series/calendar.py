from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List, override

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import homeassistant.util.dt as dt_util

from . import DOMAIN, PhilipsPetsSeriesDataUpdateCoordinator

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

    for home in coordinator.data["homes"]:
        for device in coordinator.data["devices"]:
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
        self._attr_name = f"{device.name} Meals"
        self._attr_unique_id = f"{device.id}_meal_calendar"
        self._attr_timezone = str(self.coordinator.hass.config.time_zone)
        self._events: List[CalendarEvent] = []

        _LOGGER.debug(f"Initialized calendar for device {device.id}")

    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self.device.id)},
            "name": self.device.name,
            "manufacturer": "Philips",
            "model": "Pets Series",
        }

    async def async_get_events(
        self, hass, start_date: datetime, end_date: datetime
    ) -> List[CalendarEvent]:
        """Return a list of CalendarEvent based on Meal data within the given date range."""
        events = []
        meals = self.coordinator.data.get("meals", [])

        # Use the Home Assistant timezone
        hass_timezone = dt_util.get_time_zone(self.coordinator.hass.config.time_zone)

        for meal in meals:
            if not meal.enabled:
                _LOGGER.debug("Skipping disabled meal: %s", meal.name)
                continue  # Skip disabled meals

            # Check if the meal is associated with this device
            if meal.device_id != self.device.id:
                _LOGGER.debug("Skipping meal '%s' for device %s", meal.name, meal.device_id)
                continue

            # Parse feed_time (e.g., '07:00Z')
            try:
                feed_time_naive = datetime.strptime(meal.feed_time, "%H:%MZ").time()
                feed_datetime = datetime.combine(start_date.date(), feed_time_naive)
                feed_datetime = feed_datetime.replace(tzinfo=timezone.utc)
                feed_datetime = feed_datetime.astimezone(hass_timezone)
            except ValueError as e:
                _LOGGER.error("Invalid feed_time format for meal '%s': %s", meal.name, e)
                continue

            # Map repeat_days (1=Monday, 7=Sunday) to Python's weekday (0=Monday, 6=Sunday)
            repeat_days = [day - 1 for day in meal.repeat_days if 1 <= day <= 7]
            _LOGGER.debug("Meal '%s' repeat_days: %s", meal.name, repeat_days)

            # Iterate through each day in the range and create events for matching repeat_days
            current_date = start_date.date()
            while current_date <= end_date.date():
                current_weekday = current_date.weekday()
                if current_weekday in repeat_days:
                    event_start = datetime.combine(current_date, feed_time_naive)
                    event_end = event_start + timedelta(minutes=10)

                    # Ensure event_start is timezone-aware in UTC
                    event_start_utc = dt_util.as_utc(event_start)
                    event_end_utc = dt_util.as_utc(event_end)

                    event = CalendarEvent(
                        summary=f"{meal.name} (Portion: {meal.portion_amount})",
                        start=event_start_utc,
                        end=event_end_utc,
                        description=f"Feed {meal.portion_amount} portions at {meal.feed_time}",
                        location=self.home.name,
                    )
                    events.append(event)
                    _LOGGER.debug("Added event: %s, %s - %s", event.summary, event.start, event.end)
                current_date += timedelta(days=1)

        self._events = events
        _LOGGER.debug("Generated %s events for device %s", len(events), self.device.id)
        return events

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next upcoming event."""
        now = dt_util.now()
        future_events = [event for event in self._events if event.start >= now]
        future_events.sort(key=lambda event: event.start)

        if future_events:
            next_event = future_events[0]
            return next_event
        else:
            return None