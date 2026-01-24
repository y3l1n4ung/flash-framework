"""Event definitions and listener interfaces."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .schemas import ExecutionResult, JobDefinition

logger = logging.getLogger(__name__)


class SchedulerEvent(Enum):
    """Types of events emitted by the scheduler."""

    STARTUP = "STARTUP"
    SHUTDOWN = "SHUTDOWN"

    JOB_ADDED = "JOB_ADDED"
    JOB_REMOVED = "JOB_REMOVED"
    JOB_UPDATED = "JOB_UPDATED"

    JOB_SUBMITTED = "JOB_SUBMITTED"
    JOB_EXECUTED = "JOB_EXECUTED"
    JOB_ERROR = "JOB_ERROR"
    JOB_MISSED = "JOB_MISSED"


@dataclass
class Event:
    """
    A generic event object propagated through the system.

    Attributes:
        type: The category of the event.
        timestamp: When the event occurred.
        job_id: ID of the job related to the event (optional).
        job: The job definition related to the event (optional).
        result: The execution result if the job finished (optional).
        payload: Extra catch-all data for custom event types.
    """

    type: SchedulerEvent
    timestamp: datetime
    job_id: str | None = None
    job: JobDefinition | None = None
    result: ExecutionResult | None = None
    payload: Any | None = None


class EventListener(ABC):
    """
    Interface for receiving scheduler events.
    """

    @abstractmethod
    async def on_event(self, event: Event) -> None:
        """Handle an incoming event asynchronously."""
        ...


class EventManager:
    """
    Central hub for managing listeners and dispatching events.

    Handles safe execution of listeners so one failure doesn't halt the system.
    """

    def __init__(self) -> None:
        self._listeners: list[EventListener] = []

    def add_listener(self, listener: EventListener) -> None:
        """Register a new listener to receive events."""
        if listener not in self._listeners:
            self._listeners.append(listener)

    def remove_listener(self, listener: EventListener) -> None:
        """Unregister an existing listener."""
        if listener in self._listeners:
            self._listeners.remove(listener)

    async def dispatch(self, event: Event) -> None:
        """
        Dispatch an event to all registered listeners concurrently.

        Exceptions in listeners are logged but suppressed to prevent crashing the scheduler.
        """
        if not self._listeners:
            return

        tasks = [self._safe_notify(listener, event) for listener in self._listeners]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_notify(self, listener: EventListener, event: Event) -> None:
        """Executes a single listener with error handling."""
        try:
            await listener.on_event(event)
        except Exception:
            logger.exception(f"Error in event listener {listener}")
