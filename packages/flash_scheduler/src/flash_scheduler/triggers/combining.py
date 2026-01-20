"""Combining triggers - AndTrigger and OrTrigger."""

from __future__ import annotations

from datetime import datetime, timedelta

from . import base


class AndTrigger(base.Trigger):
    """
    Trigger that fires only when ALL child triggers coincide.

    The next fire time is the earliest time when all child triggers agree to fire simultaneously.
    This uses a "leapfrog" search algorithm to find the intersection of schedules.

    Examples:
        >>> # Fire only on Mondays that are ALSO the 1st of the month
        >>> from flash_scheduler.triggers.cron import CronTrigger
        >>> trigger = AndTrigger([
        ...     CronTrigger(day_of_week="MON"),
        ...     CronTrigger(day="1"),
        ... ])

    Args:
        triggers: List of at least 2 triggers to combine.
    """

    def __init__(self, triggers: list[base.Trigger]):
        if len(triggers) < 2:
            raise ValueError("AndTrigger requires at least 2 triggers")
        self.triggers = triggers

    def next_fire_time(
        self, prev_fire_time: datetime | None, now: datetime
    ) -> datetime | None:
        """Finds the next time where all triggers overlap."""
        # Start searching from 'now'
        candidate = now

        # We subtract a tiny amount when advancing the search baseline to ensure inclusive checks.
        epsilon = timedelta(microseconds=1)
        max_iterations = 1000

        for _ in range(max_iterations):
            next_times = []

            # 1. Ask every trigger for its next fire time relative to the candidate
            for trigger in self.triggers:
                # CRITICAL FIX: We pass None here.
                # We are searching for a hypothetical future time based on 'candidate'.
                # The child trigger should not calculate based on when the parent AndTrigger last fired.
                t = trigger.next_fire_time(None, candidate)
                if t is None:
                    # If any trigger finishes its schedule, the AND condition can never be met again.
                    return None
                next_times.append(t)

            # 2. Find the earliest and latest suggestions
            furthest_time = max(next_times)
            earliest_time = min(next_times)

            # 3. If they all agree (min == max), we found our intersection!
            if furthest_time == earliest_time:
                return furthest_time

            # 4. If they disagree, we must advance.
            # The intersection CANNOT be earlier than 'furthest_time'.
            # So we set our new search baseline to just before 'furthest_time'.
            candidate = furthest_time - epsilon

        return None


class OrTrigger(base.Trigger):
    """
    Trigger that fires when ANY child trigger would fire.

    The next fire time is the earliest occurring time among all child triggers.

    Examples:
        >>> # Fire on Mondays OR on the 1st of the month
        >>> from flash_scheduler.triggers.cron import CronTrigger
        >>> trigger = OrTrigger([
        ...     CronTrigger(day_of_week="MON"),
        ...     CronTrigger(day="1"),
        ... ])

    Args:
        triggers: List of at least 2 triggers to combine.
    """

    def __init__(self, triggers: list[base.Trigger]):
        if len(triggers) < 2:
            raise ValueError("OrTrigger requires at least 2 triggers")
        self.triggers = triggers

    def next_fire_time(
        self, prev_fire_time: datetime | None, now: datetime
    ) -> datetime | None:
        """Returns the earliest next fire time from the list."""
        potential_times = []

        for trigger in self.triggers:
            # We pass None here as well to ensure we get the absolute next time
            # relative to 'now', stateless of previous runs.
            next_time = trigger.next_fire_time(None, now)
            if next_time is not None:
                potential_times.append(next_time)

        if not potential_times:
            return None

        return min(potential_times)
