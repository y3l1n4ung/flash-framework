"""CronTrigger - Fires based on cron expressions."""

from __future__ import annotations

import calendar
import random
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, ClassVar

from flash_scheduler.schemas import CronTriggerConfig

from .base import Trigger

if TYPE_CHECKING:
    import zoneinfo


class CronField:
    """Parses and matches a single cron field."""

    def __init__(
        self,
        expr: str,
        min_val: int,
        max_val: int,
        aliases: dict[str, int] | None = None,
    ):
        self.min_val = min_val
        self.max_val = max_val
        self.aliases = aliases if aliases else {}
        self.values = self._parse(expr)

    def _parse(self, expr: str) -> set[int]:
        """Parses a cron sub-expression (e.g., '*/15', '1,5', 'MON-FRI')."""
        expr = expr.upper()
        for alias, val in self.aliases.items():
            expr = expr.replace(alias, str(val))

        values = set()
        for part in expr.split(","):
            if "/" in part:
                range_part, step = part.split("/")
                step = int(step)
                if range_part == "*":
                    start, end = self.min_val, self.max_val
                elif "-" in range_part:
                    start, end = map(int, range_part.split("-"))
                else:
                    start = int(range_part)
                    end = self.max_val
                values.update(range(start, end + 1, step))

            elif "-" in part:
                start, end = map(int, part.split("-"))
                values.update(range(start, end + 1))

            elif part == "*":
                values.update(range(self.min_val, self.max_val + 1))

            else:
                values.add(int(part))

        for v in values:
            if v < self.min_val or v > self.max_val:
                msg = f"Value {v} out of range [{self.min_val}, {self.max_val}]"
                raise ValueError(
                    msg,
                )

        return values

    def matches(self, value: int) -> bool:
        return value in self.values

    def next_value(self, current: int) -> int | None:
        """Finds the next valid value greater than current."""
        for v in sorted(self.values):
            if v > current:
                return v
        return None

    def first_value(self) -> int:
        """Returns the smallest valid value."""
        return min(self.values)


class CronTrigger(Trigger):
    """
    Trigger that fires based on cron expressions.

    Format: [second] [minute] [hour] [day] [month] [day_of_week]

    Examples:
        >>> # 1. Simple: Run every 15 minutes
        >>> trigger = CronTrigger(minute="*/15")

        >>> # 2. From String (Standard Linux 5-field): Run at 5:00 AM Mondays
        >>> trigger = CronTrigger.from_string("0 5 * * MON")

        >>> # 3. From String (Extended 6-field): Run every 10 seconds
        >>> trigger = CronTrigger.from_string("*/10 * * * * *")

        >>> # 4. Jitter: Run at midnight daily with a random delay (up to 60s)
        >>> trigger = CronTrigger(hour="0", minute="0", jitter=60)

    Args:
        second: (0-59)
        minute: (0-59)
        hour: (0-23)
        day: (1-31)
        month: (1-12) or JAN-DEC
        day_of_week: (0-6) or SUN-SAT (0 is Sunday)
        tz: Timezone to calculate matches in.
        jitter: Max random delay in seconds.
    """

    DAY_ALIASES: ClassVar[dict[str, int]] = {
        "SUN": 0,
        "MON": 1,
        "TUE": 2,
        "WED": 3,
        "THU": 4,
        "FRI": 5,
        "SAT": 6,
    }
    MONTH_ALIASES: ClassVar[dict[str, int]] = {
        "JAN": 1,
        "FEB": 2,
        "MAR": 3,
        "APR": 4,
        "MAY": 5,
        "JUN": 6,
        "JUL": 7,
        "AUG": 8,
        "SEP": 9,
        "OCT": 10,
        "NOV": 11,
        "DEC": 12,
    }

    def __init__(self, config: CronTriggerConfig):
        self.second = config.second
        self.minute = config.minute
        self.hour = config.hour
        self.day = config.day
        self.month = config.month
        self.day_of_week = config.day_of_week
        self.tz = config.tz if config.tz else timezone.utc
        self.jitter = config.jitter

        # Compile fields immediately
        self._second = CronField(self.second, 0, 59)
        self._minute = CronField(self.minute, 0, 59)
        self._hour = CronField(self.hour, 0, 23)
        self._day = CronField(self.day, 1, 31)
        self._month = CronField(self.month, 1, 12, self.MONTH_ALIASES)
        self._day_of_week = CronField(self.day_of_week, 0, 6, self.DAY_ALIASES)

    @classmethod
    def from_string(
        cls,
        expr: str,
        tz: timezone | zoneinfo.ZoneInfo | None = None,
        jitter: int | None = None,
    ) -> CronTrigger:
        """
        Creates a CronTrigger from a standard cron string.

        Supports:
        - 5 fields: minute hour day month day_of_week (Standard Linux Cron)
        - 6 fields: second minute hour day month day_of_week (Extended)

        Args:
            expr: The cron expression string (e.g. "0 9 * * MON").
            tz: Timezone to use.
            jitter: Jitter in seconds.
        """
        parts = expr.split()
        num_parts = len(parts)

        if num_parts == 5:
            # Standard: min hour day month dow (seconds default to 0)
            minute, hour, day, month, dow = parts
            return cls(
                config=CronTriggerConfig(
                    minute=minute,
                    hour=hour,
                    day=day,
                    month=month,
                    day_of_week=dow,
                    tz=tz,
                    jitter=jitter,
                ),
            )
        if num_parts == 6:
            # Extended: sec min hour day month dow
            second, minute, hour, day, month, dow = parts
            return cls(
                config=CronTriggerConfig(
                    second=second,
                    minute=minute,
                    hour=hour,
                    day=day,
                    month=month,
                    day_of_week=dow,
                    tz=tz,
                    jitter=jitter,
                ),
            )
        msg = (
            f"Invalid cron expression: '{expr}'. "
            f"Expected 5 or 6 fields, got {num_parts}."
        )
        raise ValueError(
            msg,
        )

    def next_fire_time(
        self,
        prev_fire_time: datetime | None,  # noqa: ARG002
        now: datetime,
    ) -> datetime | None:
        """Finds the next matching time by iteratively advancing fields."""
        local_now = now.astimezone(self.tz)

        # Start checking 1 second in the future
        candidate = local_now.replace(microsecond=0) + timedelta(seconds=1)
        max_iterations = 1000

        for _ in range(max_iterations):
            # 1. Check Month
            if not self._month.matches(candidate.month):
                candidate = self._advance_month(candidate)
                continue

            # 2. Check Day of Month
            if not self._day.matches(candidate.day):
                candidate = self._advance_day(candidate)
                continue

            # 3. Check Day of Week (Python 0=Mon -> Cron 1=Mon)
            cron_dow = (candidate.weekday() + 1) % 7
            if not self._day_of_week.matches(cron_dow):
                candidate = self._advance_day(candidate)
                continue

            # 4. Check Hour
            if not self._hour.matches(candidate.hour):
                candidate = self._advance_hour(candidate)
                continue

            # 5. Check Minute
            if not self._minute.matches(candidate.minute):
                candidate = self._advance_minute(candidate)
                continue

            # 6. Check Second
            if not self._second.matches(candidate.second):
                candidate = self._advance_second(candidate)
                continue

            # Match found
            result = candidate.astimezone(timezone.utc)
            if self.jitter:
                result += timedelta(seconds=random.uniform(0, self.jitter))
            return result

        return None

    def _advance_month(self, dt: datetime) -> datetime:
        """Jump to the start of the next valid month."""
        next_val = self._month.next_value(dt.month)
        if next_val:
            year = dt.year
        else:
            # Wrap to next year
            next_val = self._month.first_value()
            year = dt.year + 1

        return dt.replace(year=year, month=next_val, day=1, hour=0, minute=0, second=0)

    def _advance_day(self, dt: datetime) -> datetime:
        """Jump to the start of the next day."""
        days_in_month = calendar.monthrange(dt.year, dt.month)[1]
        next_val = self._day.next_value(dt.day)

        if not next_val or next_val > days_in_month:
            return self._advance_month(dt)

        return dt.replace(day=next_val, hour=0, minute=0, second=0)

    def _advance_hour(self, dt: datetime) -> datetime:
        next_val = self._hour.next_value(dt.hour)
        if next_val is None:
            return self._advance_day(dt)
        return dt.replace(hour=next_val, minute=0, second=0)

    def _advance_minute(self, dt: datetime) -> datetime:
        next_val = self._minute.next_value(dt.minute)
        if next_val is None:
            return self._advance_hour(dt)
        return dt.replace(minute=next_val, second=0)

    def _advance_second(self, dt: datetime) -> datetime:
        next_val = self._second.next_value(dt.second)
        if next_val is None:
            return self._advance_minute(dt)
        return dt.replace(second=next_val)
