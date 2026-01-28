"""
Main Scheduler entry point.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timezone
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, Dict, Final, Set, Type

from .events import Event, EventManager, SchedulerEvent
from .executors.async_executor import AsyncExecutor
from .schemas import (
    CalendarIntervalTriggerConfig,
    CronTriggerConfig,
    DateTriggerConfig,
    ExecutionResult,
    IntervalTriggerConfig,
    JobDefinition,
    TriggerConfig,
)
from .stores.memory import MemoryJobStore
from .triggers import (
    CalendarIntervalTrigger,
    CronTrigger,
    DateTrigger,
    IntervalTrigger,
    Trigger,
)

if TYPE_CHECKING:
    from pydantic import BaseModel

    from .executors.base import BaseExecutor
    from .stores.base import JobStore

logger = logging.getLogger(__name__)

DEFAULT_CHECK_INTERVAL: Final[float] = 1.0
ERROR_BACKOFF_INTERVAL: Final[float] = 5.0


_TRIGGER_REGISTRY: Dict[Type[Any], Type[Trigger]] = {
    IntervalTriggerConfig: IntervalTrigger,
    CronTriggerConfig: CronTrigger,
    DateTriggerConfig: DateTrigger,
    CalendarIntervalTriggerConfig: CalendarIntervalTrigger,
}


def create_trigger(config: BaseModel) -> Trigger:
    """
    Create a Trigger implementation from a trigger configuration.

    Args:
        config: Trigger configuration model.

    Returns:
        Trigger implementation instance.

    Raises:
        TypeError: If the configuration type is not supported.

    Examples:
        >>> cfg = IntervalTriggerConfig(seconds=5)
        >>> trigger = create_trigger(cfg)
        >>> isinstance(trigger, Trigger)
        True
    """
    trigger_cls = _TRIGGER_REGISTRY.get(type(config))
    if not trigger_cls:
        msg = f"Unsupported trigger config: {type(config).__name__}"
        raise TypeError(msg)
    return trigger_cls(config)  # type: ignore[arg-type]


class FlashScheduler:
    """
    Asynchronous job scheduler with concurrent execution prevention.

    This scheduler manages periodic job execution with support for multiple
    trigger types (interval, cron, date-based). It prevents concurrent execution
    of the same job and provides event-driven notifications for all job lifecycle
    events.

    Examples:
        >>> import asyncio
        >>> from flash_scheduler import FlashScheduler
        >>> from flash_scheduler.schemas import IntervalTriggerConfig
        >>>
        >>> scheduler = FlashScheduler()
        >>>
        >>> @scheduler.task(IntervalTriggerConfig(seconds=1))
        ... async def heartbeat():
        ...     print("tick")
        >>>
        >>> async def main():
        ...     await scheduler.start()
        ...     await asyncio.sleep(3)
        ...     await scheduler.shutdown()
        >>>
        >>> asyncio.run(main())
    """

    def __init__(
        self,
        store: JobStore | None = None,
        executor: BaseExecutor | None = None,
        event_manager: EventManager | None = None,
    ) -> None:
        """
        Initialize the scheduler with optional custom backends.

        Args:
            store: Job storage backend. Defaults to MemoryJobStore.
            executor: Job execution backend. Defaults to AsyncExecutor.
            event_manager: Event dispatcher. Defaults to EventManager.

        Raises:
            ValueError: If provided backends have incompatible interfaces.
        """
        if store is not None and not hasattr(store, "add_job"):
            msg = "Store must implement JobStore interface"
            raise ValueError(msg)
        if executor is not None and not hasattr(executor, "submit_job"):
            msg = "Executor must implement BaseExecutor interface"
            raise ValueError(msg)

        self.store = store or MemoryJobStore()
        self.executor = executor or AsyncExecutor()
        self.events = event_manager or EventManager()

        self._running = False
        self._main_task: asyncio.Task[None] | None = None
        self._wakeup = asyncio.Event()
        self._pending_jobs: list[JobDefinition] = []
        self._active_executions: Set[asyncio.Task[None]] = set()
        self._running_jobs: Set[str] = set()

    def task(
        self,
        trigger: TriggerConfig,
        job_id: str | None = None,
        name: str | None = None,
        args: list[Any] | None = None,
        kwargs: dict[str, Any] | None = None,
        enabled: bool = True,
    ):
        """
        Register a function as a scheduled task via decorator.

        The decorated function is not registered to the store until start()
        is called, allowing for flexible initialization patterns.

        Args:
            trigger: Trigger configuration (interval, cron, date, etc).
            job_id: Unique job identifier. Auto-generated from module.function.
            name: Human-readable job name. Defaults to function name.
            args: Default positional arguments for execution.
            kwargs: Default keyword arguments for execution.
            enabled: Whether the job is enabled at registration.

        Returns:
            Decorated async callable.

        Raises:
            ValueError: If job_id is empty or exceeds 255 characters.

        Examples:
            >>> @scheduler.task(IntervalTriggerConfig(seconds=2))
            ... async def simple_job():
            ...     print("running")

            >>> @scheduler.task(
            ...     IntervalTriggerConfig(minutes=5),
            ...     job_id="email_digest",
            ...     args=["admin@example.com"],
            ...     kwargs={"priority": "high"}
            ... )
            ... async def send_notification(email, priority="normal"):
            ...     pass
        """

        def decorator(func: Callable):
            func_name = getattr(func, "__name__", "unnamed_task")
            func_module = getattr(func, "__module__", "unknown_module")

            final_job_id = job_id or f"{func_module}.{func_name}"

            if not final_job_id or len(final_job_id) > 255:
                msg = f"Job ID must be 1-255 characters, got '{final_job_id}'"
                raise ValueError(
                    msg,
                )

            func_ref = f"{func_module}:{func_name}"

            job = JobDefinition(
                job_id=final_job_id,
                name=name or func_name,
                func_ref=func_ref,
                trigger=trigger,
                args=args or [],
                kwargs=kwargs or {},
                enabled=enabled,
            )

            self._pending_jobs.append(job)

            @wraps(func)
            async def wrapper(*w_args, **w_kwargs):
                return await func(*w_args, **w_kwargs)

            return wrapper

        return decorator

    async def start(self) -> None:
        """
        Start the scheduler and begin job execution.

        Performs the following:
        1. Starts the executor backend
        2. Registers all pending decorator-defined jobs
        3. Emits STARTUP event
        4. Creates the main event loop task

        Raises:
            RuntimeError: If executor fails to start.
        """
        if self._running:
            return

        try:
            await self.executor.start()
        except Exception as e:
            logger.exception("Failed to start executor", exc_info=e)
            msg = "Executor startup failed"
            raise RuntimeError(msg) from e

        self._running = True

        for job in self._pending_jobs:
            await self.add_job(job)

        self._pending_jobs.clear()

        await self.events.dispatch(
            Event(type=SchedulerEvent.STARTUP, timestamp=datetime.now(timezone.utc)),
        )

        self._main_task = asyncio.create_task(self._run_loop())

    async def shutdown(self, wait: bool = True) -> None:
        """
        Shut down the scheduler and stop job execution.

        Performs the following:
        1. Marks scheduler as stopped
        2. Cancels the main loop task
        3. Optionally waits for active job executions
        4. Shuts down executor
        5. Emits SHUTDOWN event

        Args:
            wait: If True, waits for active executions to complete.
                  If False, cancels them immediately.
        """
        if not self._running:
            return

        self._running = False
        self._wakeup.set()

        if self._main_task:
            self._main_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._main_task

        if wait and self._active_executions:
            try:
                await asyncio.gather(
                    *list(self._active_executions),
                    return_exceptions=True,
                )
            except Exception as e:
                logger.warning("Error waiting for active executions", exc_info=e)

        await self.executor.shutdown(wait=wait)

        await self.events.dispatch(
            Event(type=SchedulerEvent.SHUTDOWN, timestamp=datetime.now(timezone.utc)),
        )

    async def add_job(self, job: JobDefinition) -> None:
        """
        Add or update a job definition in the scheduler.

        If job_id already exists in store, updates it. Otherwise adds new.
        Enabled jobs are automatically scheduled with next_run_time set.
        Disabled jobs are stored but not scheduled.

        Args:
            job: JobDefinition with id, trigger, func_ref, etc.

        Raises:
            ValueError: If job_id is invalid or job definition is incomplete.
            RuntimeError: If store operation fails.
        """
        if not job or not job.job_id:
            msg = "Job and job_id are required"
            raise ValueError(msg)

        now = datetime.now(timezone.utc)

        try:
            existing = await self.store.get_job(job.job_id)
            event_type = (
                SchedulerEvent.JOB_UPDATED if existing else SchedulerEvent.JOB_ADDED
            )

            if not existing:
                await self.store.add_job(job)

            await self.store.update_job(job)

            await self.events.dispatch(
                Event(
                    type=event_type,
                    timestamp=datetime.now(timezone.utc),
                    job=job,
                    job_id=job.job_id,
                ),
            )

            if job.enabled:
                trigger = create_trigger(job.trigger)
                first_run = trigger.next_fire_time(None, now)
                await self.store.set_next_run_time(job.job_id, first_run)

            self._wakeup.set()

        except Exception as e:
            logger.exception("Failed to add job %s", job.job_id, exc_info=e)
            msg = f"Failed to add job: {e}"
            raise RuntimeError(msg) from e

    async def remove_job(self, job_id: str) -> None:
        """
        Remove a job from the scheduler.

        The job is immediately removed from the store and cannot be executed.
        If the job is currently running, it continues to completion but is
        not rescheduled.

        Args:
            job_id: Identifier of job to remove.

        Raises:
            ValueError: If job_id is invalid.
        """
        if not job_id:
            msg = "job_id is required"
            raise ValueError(msg)

        started_at = datetime.now(timezone.utc)

        try:
            job = await self.store.get_job(job_id)
            success = await self.store.remove_job(job_id)

            await self.events.dispatch(
                Event(
                    type=SchedulerEvent.JOB_REMOVED,
                    timestamp=datetime.now(timezone.utc),
                    job_id=job_id,
                    job=job,
                    result=ExecutionResult(
                        job_id=job_id,
                        success=success,
                        return_value=success,
                        started_at=started_at,
                        finished_at=datetime.now(timezone.utc),
                    ),
                ),
            )

        except Exception as e:
            logger.exception("Failed to remove job %s", job_id, exc_info=e)
            msg = f"Failed to remove job: {e}"
            raise RuntimeError(msg) from e

    async def _run_loop(self) -> None:
        """
        Main scheduler loop running continuously while scheduler is active.

        For each iteration:
        1. Gets jobs due for execution at current time
        2. Skips disabled jobs and already-running jobs
        3. Reschedules job based on trigger configuration
        4. Creates execution task and tracks it
        5. Waits for timeout or wakeup signal

        Errors in the loop trigger exponential backoff recovery (5s vs 1s normal).
        """
        while self._running:
            try:
                now = datetime.now(timezone.utc)
                due_jobs = await self.store.get_due_jobs(now)

                for job in due_jobs:
                    if not job.enabled:
                        continue

                    if job.job_id in self._running_jobs:
                        continue

                    self._running_jobs.add(job.job_id)

                    scheduled_time = await self.store.get_next_run_time(job.job_id)
                    trigger = create_trigger(job.trigger)

                    base_time = scheduled_time or now
                    next_run = trigger.next_fire_time(base_time, now)

                    await self.store.set_next_run_time(job.job_id, next_run)

                    task = asyncio.create_task(self._execute_and_notify(job))
                    self._active_executions.add(task)

                    def _cleanup(t: asyncio.Task, jid: str = job.job_id) -> None:
                        self._running_jobs.discard(jid)
                        self._active_executions.discard(t)

                    task.add_done_callback(_cleanup)

                try:
                    await asyncio.wait_for(
                        self._wakeup.wait(),
                        timeout=DEFAULT_CHECK_INTERVAL,
                    )
                except asyncio.TimeoutError:
                    pass
                finally:
                    self._wakeup.clear()

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Scheduler loop error", exc_info=exc)
                try:
                    await asyncio.wait_for(
                        self._wakeup.wait(),
                        timeout=ERROR_BACKOFF_INTERVAL,
                    )
                except asyncio.TimeoutError:
                    pass
                finally:
                    self._wakeup.clear()

    async def _execute_and_notify(self, job: JobDefinition) -> None:
        """
        Execute a job and emit lifecycle events.

        Sequence:
        1. Validates job still exists and is enabled in store
        2. Emits JOB_SUBMITTED event
        3. Submits job to executor
        4. Emits JOB_EXECUTED (success) or JOB_ERROR (failure)

        Args:
            job: JobDefinition to execute.
        """
        job_state = await self.store.get_job(job.job_id)
        if not job_state or not job_state.enabled:
            return

        await self.events.dispatch(
            Event(
                type=SchedulerEvent.JOB_SUBMITTED,
                timestamp=datetime.now(timezone.utc),
                job_id=job.job_id,
                job=job,
            ),
        )

        result: ExecutionResult = await self.executor.submit_job(job)

        event_type = (
            SchedulerEvent.JOB_EXECUTED if result.success else SchedulerEvent.JOB_ERROR
        )

        await self.events.dispatch(
            Event(
                type=event_type,
                timestamp=datetime.now(timezone.utc),
                job_id=job.job_id,
                job=job,
                result=result,
            ),
        )
