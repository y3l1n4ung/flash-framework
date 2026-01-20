"""
Domain - Trigger System.

Triggers are pure functions that compute the next fire time based on:
- Previous fire time (or None for first execution)
- Current time (now)

All triggers are deterministic - same inputs always produce same outputs.
No I/O, no asyncio calls, no side effects.
"""

from typing import Any, Type, Dict, Union


from .base import Trigger
from .calendar import CalendarIntervalTrigger
from .cron import CronTrigger
from .date import DateTrigger
from .interval import IntervalTrigger
from .combining import AndTrigger, OrTrigger


__all__ = [
    "Trigger",
    "IntervalTrigger",
    "CalendarIntervalTrigger",
    "CronTrigger",
    "DateTrigger",
    "AndTrigger",
    "OrTrigger",
]
