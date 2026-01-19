"""DateTrigger - Fires once at a specific datetime."""

from __future__ import annotations

from datetime import datetime

from . import base


class DateTrigger(base.Trigger):
    """
    Trigger that fires exactly once at a specific datetime.

    Examples:
        >>> # Run once on Jan 1st, 2026 at 9:00 AM UTC
        >>> from datetime import timezone
        >>> run_time = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
        >>> trigger = DateTrigger(run_time=run_time)

    Args:
        run_time: The exact time the job should run. Must be timezone-aware.
    """

    def __init__(self, run_time: datetime):
        if run_time.tzinfo is None:
            raise ValueError("run_time must be timezone-aware")
        self.run_time = run_time

    def next_fire_time(
        self, prev_fire_time: datetime | None, now: datetime
    ) -> datetime | None:
        """Calculates the next scheduled time."""
        # Case 1: Already ran (DateTrigger only runs once)
        if prev_fire_time is not None:
            return None

        # Case 2: The scheduled time is in the past
        # (We skip it to avoid executing old, stale jobs immediately upon startup)
        if self.run_time <= now:
            return None

        return self.run_time
