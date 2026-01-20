"""IntervalTrigger - Fires at fixed time intervals."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from flash_scheduler.schemas import IntervalTriggerConfig

from .base import Trigger


class IntervalTrigger(Trigger):
    """
    Trigger that fires at fixed time intervals.

    Examples:
        >>> # 1. Simple: Run every 30 seconds
        >>> trigger = IntervalTrigger(seconds=30)

        >>> # 2. Complex: Run every 1 week and 12 hours
        >>> trigger = IntervalTrigger(weeks=1, hours=12)

        >>> # 3. Jitter: Run every 5 minutes with 10s random delay
        >>> trigger = IntervalTrigger(minutes=5, jitter=10)

        >>> # 4. Time Window: Run every hour, but only between 9am and 5pm
        >>> # (Note: usually set on the Job, but Trigger supports it too)
        >>> start = datetime(2024, 1, 1, 9, 0)
        >>> trigger = IntervalTrigger(hours=1, start_time=start)

    Args:
        weeks: Number of weeks to wait.
        days: Number of days to wait.
        hours: Number of hours to wait.
        minutes: Number of minutes to wait.
        seconds: Number of seconds to wait.
        interval: Direct timedelta object (optional). If provided, overrides unit arguments.
        start_time: Earliest possible fire time.
        end_time: Latest possible fire time.
        jitter: Max random delay in seconds to avoid load spikes.
    """

    def __init__(self, config: IntervalTriggerConfig):
        if config.interval:
            self.interval = config.interval
        else:
            self.interval = timedelta(
                weeks=config.weeks,
                days=config.days,
                hours=config.hours,
                minutes=config.minutes,
                seconds=config.seconds,
            )

        self.start_time = config.start_time
        self.end_time = config.end_time
        self.jitter = config.jitter

    def next_fire_time(
        self, prev_fire_time: datetime | None, now: datetime
    ) -> datetime | None:
        """Calculates the next scheduled time."""
        if self.end_time and now >= self.end_time:
            return None

        # Case 1: First Run (Job has never executed)
        if prev_fire_time is None:
            if self.start_time and self.start_time > now:
                # If a future start_time is set, wait until then
                next_fire = self.start_time
            else:
                # Otherwise, start counting the interval from right now
                next_fire = now + self.interval

        # Case 2: Subsequent Run (Job ran previously)
        else:
            next_fire = prev_fire_time + self.interval

            # Catch-up Logic: If we missed execution windows (e.g. downtime),
            # jump forward to the next valid slot relative to the previous run.
            if next_fire < now:
                delta_diff = now - prev_fire_time
                intervals_missed = delta_diff // self.interval
                next_fire = prev_fire_time + (self.interval * (intervals_missed + 1))

        # Apply Jitter
        if self.jitter:
            next_fire += timedelta(seconds=random.uniform(0, self.jitter))

        # Final bounds check
        if self.end_time and next_fire > self.end_time:
            return None

        return next_fire
