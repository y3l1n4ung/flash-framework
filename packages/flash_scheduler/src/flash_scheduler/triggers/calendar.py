"""CalendarIntervalTrigger - Fires at calendar-aware intervals."""

from __future__ import annotations

import calendar
import random
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from .base import Trigger

if TYPE_CHECKING:
    from flash_scheduler.schemas import CalendarIntervalTriggerConfig


class CalendarIntervalTrigger(Trigger):
    """
    Trigger that fires at intervals respecting calendar boundaries.

    Examples:
        >>> # Monthly execution on a specific time
        >>> config = CalendarIntervalTriggerConfig(months=1, hour=9, minute=0)
        >>> trigger = CalendarIntervalTrigger(config)

        >>> # Weekly execution
        >>> config = CalendarIntervalTriggerConfig(weeks=1, hour=12)
        >>> trigger = CalendarIntervalTrigger(config)

        >>> # Complex calendar interval (every 3 months and 2 days)
        >>> config = CalendarIntervalTriggerConfig(months=3, days=2, hour=0)
        >>> trigger = CalendarIntervalTrigger(config)

    Args:
        config: CalendarIntervalTriggerConfig,
    """

    def __init__(
        self,
        config: CalendarIntervalTriggerConfig,
    ):
        self.years = config.years
        self.months = config.months
        self.weeks = config.weeks
        self.days = config.days
        self.hour = config.hour
        self.minute = config.minute
        self.second = config.second
        self.start_time = config.start_time
        self.end_time = config.end_time
        self.tz = config.tz or timezone.utc
        self.jitter = config.jitter

    def next_fire_time(
        self,
        prev_fire_time: datetime | None,
        now: datetime,
    ) -> datetime | None:
        """Calculates the next scheduled time."""
        if self.end_time and now >= self.end_time:
            return None

        # Normalize 'now' to trigger timezone
        local_now = now.astimezone(self.tz)

        if prev_fire_time is None:
            # First execution calculation
            if self.start_time:
                next_fire = self.start_time.astimezone(self.tz)
            else:
                next_fire = local_now.replace(
                    hour=self.hour,
                    minute=self.minute,
                    second=self.second,
                    microsecond=0,
                )

            if next_fire <= local_now:
                next_fire = self._add_interval(next_fire)
        else:
            # Subsequent execution
            previous_local = prev_fire_time.astimezone(self.tz)
            next_fire = self._add_interval(previous_local)

            while next_fire <= local_now:
                next_fire = self._add_interval(next_fire)

        # Apply Jitter (in UTC)
        result = next_fire.astimezone(timezone.utc)
        if self.jitter:
            result += timedelta(seconds=random.uniform(0, self.jitter))

        if self.end_time and result > self.end_time:
            return None

        return result

    def _add_interval(self, dt: datetime) -> datetime:
        """Adds years/months safely using the calendar module."""
        year = dt.year + self.years

        # Calculate months
        total_months = (dt.month - 1) + self.months
        year += total_months // 12
        month = (total_months % 12) + 1

        # Clip days (e.g. Feb 30 -> Feb 28)
        days_in_month = calendar.monthrange(year, month)[1]
        day = min(dt.day, days_in_month)

        new_dt = dt.replace(year=year, month=month, day=day)

        if self.weeks or self.days:
            new_dt += timedelta(weeks=self.weeks, days=self.days)

        return new_dt

    def __repr__(self) -> str:
        return (
            f"CalendarIntervalTrigger(years={self.years}, months={self.months}, "
            f"weeks={self.weeks}, days={self.days}, "
            f"time='{self.hour:02}:{self.minute:02}:{self.second:02}', "
            f"tz={self.tz}, 'jitter={self.jitter}')"
        )
