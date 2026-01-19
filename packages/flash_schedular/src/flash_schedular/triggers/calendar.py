"""CalendarIntervalTrigger - Fires at calendar-aware intervals."""

from __future__ import annotations

import calendar
import random
from datetime import datetime, timedelta, timezone

from .base import Trigger


class CalendarIntervalTrigger(Trigger):
    """
    Trigger that fires at intervals respecting calendar boundaries.

    Unlike standard intervals, this handles variable month lengths and leap years
    correctly (e.g., "every month" on Jan 31st -> Feb 28th/29th).

    Examples:
        >>> # Run on the 1st of every month at 9:00 AM UTC
        >>> trigger = CalendarIntervalTrigger(months=1, hour=9, minute=0)

        >>> # Run yearly with a random delay (jitter) to prevent load spikes
        >>> trigger = CalendarIntervalTrigger(years=1, jitter=60)

    Args:
        years: Interval in years.
        months: Interval in months.
        weeks: Interval in weeks.
        days: Interval in days.
        hour: Hour to fire on (0-23).
        minute: Minute to fire on (0-59).
        second: Second to fire on (0-59).
        start_time: Earliest possible fire time.
        end_time: Latest possible fire time.
        tz: Timezone to use for calculations.
        jitter: Max random delay in seconds to avoid load spikes.
    """

    def __init__(
        self,
        years: int = 0,
        months: int = 0,
        weeks: int = 0,
        days: int = 0,
        hour: int = 0,
        minute: int = 0,
        second: int = 0,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        tz: timezone | None = None,
        jitter: int | None = None,
    ):
        if not any((years, months, weeks, days)):
            raise ValueError(
                "Must specify at least one interval (years, months, weeks, or days)."
            )

        self.years = years
        self.months = months
        self.weeks = weeks
        self.days = days
        self.hour = hour
        self.minute = minute
        self.second = second
        self.start_time = start_time
        self.end_time = end_time
        self.tz = tz or timezone.utc
        self.jitter = jitter

    def next_fire_time(
        self, prev_fire_time: datetime | None, now: datetime
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
            f"time='{self.hour:02}:{self.minute:02}:{self.second:02}', tz={self.tz}, 'jitter={self.jitter}')"
        )
