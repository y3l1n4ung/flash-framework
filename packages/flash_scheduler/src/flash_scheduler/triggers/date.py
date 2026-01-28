"""DateTrigger - Fires once at a specific datetime."""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import base

if TYPE_CHECKING:
    from datetime import datetime


class DateTrigger(base.Trigger):
    """
    Trigger that fires exactly once at a specific datetime.

    Examples:
        >>> # Run once on Jan 1st, 2026 at 9:00 AM UTC
        >>> from datetime import timezone
        >>> run_at = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
        >>> trigger = DateTrigger(run_at=run_at)

    Args:
        run_at: The exact time the job should run. Must be timezone-aware.
    """

    def __init__(self, run_at: datetime):
        if run_at.tzinfo is None:
            msg = "run_at must be timezone-aware"
            raise ValueError(msg)
        self.run_at = run_at

    def next_fire_time(
        self,
        prev_fire_time: datetime | None,
        now: datetime,
    ) -> datetime | None:
        """Calculates the next scheduled time."""
        # Case 1: Already ran (DateTrigger only runs once)
        if prev_fire_time is not None:
            return None

        # Case 2: The scheduled time is in the past
        # (We skip it to avoid executing old, stale jobs immediately upon startup)
        if self.run_at <= now:
            return None

        return self.run_at
