"""
Domain - Trigger System.

Triggers are pure functions that compute the next fire time based on:
- Previous fire time (or None for first execution)
- Current time (now)

"""

from .base import Trigger
from .calendar import CalendarIntervalTrigger
from .combining import AndTrigger, OrTrigger
from .cron import CronTrigger
from .date import DateTrigger
from .interval import IntervalTrigger

__all__ = [
    "Trigger",
    "IntervalTrigger",
    "CalendarIntervalTrigger",
    "CronTrigger",
    "DateTrigger",
    "AndTrigger",
    "OrTrigger",
]
