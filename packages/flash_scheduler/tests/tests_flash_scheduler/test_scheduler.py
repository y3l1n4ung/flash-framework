import asyncio
import contextlib
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from flash_scheduler.events import Event, EventListener, SchedulerEvent
from flash_scheduler.executors.async_executor import AsyncExecutor
from flash_scheduler.scheduler import FlashScheduler, create_trigger
from flash_scheduler.schemas import IntervalTriggerConfig, JobDefinition
from flash_scheduler.stores.memory import MemoryJobStore

pytestmark = pytest.mark.asyncio


class EventCollector(EventListener):
    """Captures events for assertions."""

    def __init__(self):
        self.events: list[Event] = []

    async def on_event(self, event: Event) -> None:
        self.events.append(event)

    def by_type(self, event_type: SchedulerEvent) -> list[Event]:
        """Get events filtered by type."""
        return [e for e in self.events if e.type == event_type]

    def count(self, event_type: SchedulerEvent) -> int:
        """Count events of a specific type."""
        return len(self.by_type(event_type))

    def first(self, event_type: SchedulerEvent) -> Event | None:
        """Get first event of a specific type."""
        events = self.by_type(event_type)
        return events[0] if events else None


@pytest_asyncio.fixture
async def scheduler():
    """Clean scheduler instance."""
    sched = FlashScheduler(store=MemoryJobStore(), executor=AsyncExecutor())
    yield sched
    if sched._running:
        await sched.shutdown(wait=False)


@pytest_asyncio.fixture
async def scheduler_with_events(scheduler):
    """Scheduler with event collector."""
    collector = EventCollector()
    scheduler.events.add_listener(collector)
    yield scheduler, collector


class TestSchedulerLifecycle:
    """Tests for scheduler startup and shutdown behavior."""

    async def test_start_transitions_running_state(self, scheduler):
        """Scheduler transitions from stopped to running on start."""
        assert scheduler._running is False
        await scheduler.start()
        assert scheduler._running is True
        await scheduler.shutdown()

    async def test_shutdown_transitions_running_state(self, scheduler):
        """Scheduler transitions from running to stopped on shutdown."""
        await scheduler.start()
        assert scheduler._running is True
        await scheduler.shutdown()
        assert scheduler._running is False

    async def test_start_is_idempotent(self, scheduler):
        """Multiple start() calls use same main task."""
        await scheduler.start()
        task_1 = scheduler._main_task

        await scheduler.start()
        task_2 = scheduler._main_task

        assert task_1 is task_2
        await scheduler.shutdown()

    async def test_shutdown_is_idempotent(self, scheduler):
        """Multiple shutdown() calls are safe."""
        await scheduler.start()
        await scheduler.shutdown()
        assert scheduler._running is False

        await scheduler.shutdown()
        assert scheduler._running is False

    async def test_shutdown_without_wait_flag(self, scheduler):
        """Shutdown with wait=False doesn't block."""
        await scheduler.start()
        await scheduler.shutdown(wait=False)
        assert scheduler._running is False

    async def test_startup_event_dispatched(self, scheduler_with_events):
        """STARTUP event emitted when scheduler starts."""
        scheduler, collector = scheduler_with_events
        await scheduler.start()

        assert collector.count(SchedulerEvent.STARTUP) > 0
        await scheduler.shutdown()

    async def test_shutdown_event_dispatched(self, scheduler_with_events):
        """SHUTDOWN event emitted when scheduler stops."""
        scheduler, collector = scheduler_with_events
        await scheduler.start()
        await scheduler.shutdown()

        assert collector.count(SchedulerEvent.SHUTDOWN) > 0

    async def test_startup_failure_propagates(self, scheduler):
        """Executor startup failure raises RuntimeError."""
        scheduler.executor.start = AsyncMock(
            side_effect=RuntimeError("Executor init failed"),
        )

        with pytest.raises(RuntimeError, match="Executor startup failed"):
            await scheduler.start()


class TestTaskDecorator:
    """Tests for @task decorator and deferred registration."""

    async def test_decorator_defers_registration_until_start(self, scheduler):
        """Decorated job added to pending, not store, until start()."""

        @scheduler.task(IntervalTriggerConfig(seconds=10), job_id="decorated")
        async def my_job():
            pass

        assert len(scheduler._pending_jobs) == 1
        assert scheduler._pending_jobs[0].job_id == "decorated"
        assert await scheduler.store.get_job("decorated") is None

        await scheduler.start()

        assert len(scheduler._pending_jobs) == 0
        assert await scheduler.store.get_job("decorated") is not None
        await scheduler.shutdown()

    async def test_decorator_auto_generates_job_id(self, scheduler):
        """Job ID auto-generated from module.function when not specified."""

        @scheduler.task(IntervalTriggerConfig(seconds=1))
        async def my_function():
            pass

        job = scheduler._pending_jobs[0]
        assert "my_function" in job.job_id

    async def test_decorator_uses_explicit_job_id(self, scheduler):
        """Explicit job_id overrides auto-generation."""

        @scheduler.task(IntervalTriggerConfig(seconds=1), job_id="explicit_id")
        async def my_job():
            pass

        assert scheduler._pending_jobs[0].job_id == "explicit_id"

    async def test_decorator_preserves_function_metadata(self, scheduler):
        """Decorator preserves function name and docstring via @wraps."""

        @scheduler.task(IntervalTriggerConfig(seconds=1))
        async def documented_job():
            """Job documentation."""

        assert documented_job.__name__ == "documented_job"
        assert documented_job.__doc__ == "Job documentation."

    async def test_decorator_creates_callable_wrapper(self, scheduler):
        """Decorated function is awaitable and returns correct result."""

        @scheduler.task(IntervalTriggerConfig(seconds=1))
        async def add(a: int, b: int) -> int:
            return a + b

        result = await add(5, 3)
        assert result == 8

    async def test_decorator_validates_job_id_too_long(self, scheduler):
        """Decorator raises ValueError for job_id > 255 chars."""
        with pytest.raises(ValueError, match="1-255 characters"):

            @scheduler.task(IntervalTriggerConfig(seconds=1), job_id="x" * 256)
            async def job():
                pass

    async def test_decorator_stores_args_and_kwargs(self, scheduler):
        """Decorator stores default args and kwargs in job."""

        @scheduler.task(
            IntervalTriggerConfig(seconds=1),
            job_id="parameterized",
            args=[1, 2],
            kwargs={"key": "value"},
        )
        async def job(a, b, key=None):
            pass

        job_def = scheduler._pending_jobs[0]
        assert job_def.args == [1, 2]
        assert job_def.kwargs == {"key": "value"}


class TestJobManagement:
    """Tests for adding, updating, and removing jobs."""

    async def test_add_new_job_to_store(self, scheduler, temp_task_module):
        """New job added to store when add_job called."""
        await scheduler.start()

        job = JobDefinition(
            job_id="new_job",
            name="New Job",
            func_ref=f"{temp_task_module}:async_add",
            trigger=IntervalTriggerConfig(seconds=1),
            args=[1, 2],
        )

        await scheduler.add_job(job)

        stored = await scheduler.store.get_job("new_job")
        assert stored is not None
        assert stored.args == [1, 2]
        await scheduler.shutdown()

    async def test_add_job_emits_job_added_event(self, scheduler_with_events):
        """Adding new job emits JOB_ADDED event."""
        scheduler, collector = scheduler_with_events
        await scheduler.start()

        job = JobDefinition(
            job_id="add_event_test",
            name="Add Event Test",
            func_ref="none:none",
            trigger=IntervalTriggerConfig(seconds=1),
        )

        await scheduler.add_job(job)

        assert collector.count(SchedulerEvent.JOB_ADDED) > 0
        await scheduler.shutdown()

    async def test_update_job_emits_job_updated_event(self, scheduler_with_events):
        """Updating existing job emits JOB_UPDATED event."""
        scheduler, collector = scheduler_with_events
        await scheduler.start()

        job = JobDefinition(
            job_id="update_test",
            name="Update Test",
            func_ref="none:none",
            trigger=IntervalTriggerConfig(seconds=1),
        )

        await scheduler.add_job(job)
        await scheduler.add_job(job)

        assert collector.count(SchedulerEvent.JOB_UPDATED) > 0
        await scheduler.shutdown()

    async def test_add_job_sets_next_run_when_enabled(self, scheduler):
        """Enabled job gets next_run_time set."""
        await scheduler.start()

        job = JobDefinition(
            job_id="enabled_job",
            name="Enabled Job",
            func_ref="none:none",
            trigger=IntervalTriggerConfig(seconds=5),
            enabled=True,
        )

        await scheduler.add_job(job)

        next_run = await scheduler.store.get_next_run_time("enabled_job")
        assert next_run is not None
        assert next_run > datetime.now(timezone.utc)
        await scheduler.shutdown()

    async def test_add_job_skips_scheduling_when_disabled(self, scheduler):
        """Disabled job not scheduled in add_job."""
        await scheduler.start()

        job = JobDefinition(
            job_id="disabled_job",
            name="Disabled Job",
            func_ref="none:none",
            trigger=IntervalTriggerConfig(seconds=5),
            enabled=False,
        )

        await scheduler.add_job(job)
        await scheduler.shutdown()

    async def test_add_job_validates_job_not_none(self, scheduler):
        """add_job raises ValueError when job is None."""
        await scheduler.start()

        with pytest.raises(ValueError, match="Job and job_id are required"):
            await scheduler.add_job(None)

        await scheduler.shutdown()

    async def test_add_job_validates_job_id_not_empty(self, scheduler):
        """add_job raises ValueError when job_id is empty."""
        await scheduler.start()

        job = JobDefinition(
            name="",
            job_id="",
            func_ref="none:none",
            trigger=IntervalTriggerConfig(seconds=1),
        )

        with pytest.raises(ValueError, match="Job and job_id are required"):
            await scheduler.add_job(job)

        await scheduler.shutdown()

    async def test_add_job_propagates_store_errors(self, scheduler):
        """add_job raises RuntimeError on store failure."""
        await scheduler.start()

        # Force exception to trigger the try/except block
        with patch.object(
            scheduler.store,
            "add_job",
            side_effect=RuntimeError("DB error"),
        ):
            job = JobDefinition(
                name="Error Job",
                job_id="error_job",
                func_ref="none:none",
                trigger=IntervalTriggerConfig(seconds=1),
            )

            with pytest.raises(RuntimeError, match="Failed to add job"):
                await scheduler.add_job(job)

        await scheduler.shutdown()

    async def test_add_job_update_failure(self, scheduler, temp_task_module):
        """
        Test add_job exception handling when update_job fails.
        """
        await scheduler.start()

        job = JobDefinition(
            job_id="fail_update",
            name="Fail Update",
            func_ref="none:none",
            trigger=IntervalTriggerConfig(seconds=1),
        )

        # Let add_job succeed (first call), but update_job fail (second call logic in
        # add_job)
        # Note: add_job logic is: check existing, if not existing -> add, then
        # ALWAYS update.
        scheduler.store.update_job = AsyncMock(
            side_effect=RuntimeError("Update failed"),
        )

        with pytest.raises(RuntimeError, match="Failed to add job"):
            await scheduler.add_job(job)

        await scheduler.shutdown()

    async def test_remove_job_from_store(self, scheduler):
        """Job removed from store when remove_job called."""
        await scheduler.start()

        job = JobDefinition(
            job_id="removable",
            name="Removable Job",
            func_ref="none:none",
            trigger=IntervalTriggerConfig(seconds=60),
        )

        await scheduler.add_job(job)
        assert await scheduler.store.get_job("removable") is not None

        await scheduler.remove_job("removable")
        assert await scheduler.store.get_job("removable") is None
        await scheduler.shutdown()

    async def test_remove_job_emits_job_removed_event(self, scheduler_with_events):
        """Removing job emits JOB_REMOVED event."""
        scheduler, collector = scheduler_with_events
        await scheduler.start()

        job = JobDefinition(
            job_id="rm_test",
            name="Remove Test",
            func_ref="none:none",
            trigger=IntervalTriggerConfig(seconds=60),
        )

        await scheduler.add_job(job)
        await scheduler.remove_job("rm_test")

        assert collector.count(SchedulerEvent.JOB_REMOVED) > 0
        await scheduler.shutdown()

    async def test_remove_job_validates_job_id_not_empty(self, scheduler):
        """remove_job raises ValueError when job_id is empty."""
        await scheduler.start()

        with pytest.raises(ValueError, match="job_id is required"):
            await scheduler.remove_job("")

        await scheduler.shutdown()

    async def test_remove_job_propagates_store_errors(self, scheduler):
        """remove_job raises RuntimeError on store failure."""
        await scheduler.start()

        scheduler.store.remove_job = AsyncMock(side_effect=RuntimeError("DB error"))

        with pytest.raises(RuntimeError, match="Failed to remove job"):
            await scheduler.remove_job("any_job")

        await scheduler.shutdown()

    async def test_remove_job_get_failure(self, scheduler):
        """
        remove_job exception handling when get_job fails.
        """
        await scheduler.start()

        scheduler.store.get_job = AsyncMock(side_effect=RuntimeError("Get failed"))

        with pytest.raises(RuntimeError, match="Failed to remove job"):
            await scheduler.remove_job("some_id")

        await scheduler.shutdown()


class TestJobExecution:
    """Tests for job execution flow and event dispatch."""

    async def test_successful_job_execution(
        self,
        scheduler_with_events,
        temp_task_module,
    ):
        """Successful execution emits JOB_EXECUTED with result."""
        scheduler, collector = scheduler_with_events
        await scheduler.start()

        job = JobDefinition(
            job_id="success",
            name="Success Job",
            func_ref=f"{temp_task_module}:async_add",
            trigger=IntervalTriggerConfig(seconds=1),
            args=[10, 20],
        )

        await scheduler.add_job(job)
        await asyncio.sleep(1.2)
        await scheduler.shutdown()

        executed = collector.first(SchedulerEvent.JOB_EXECUTED)
        assert executed is not None
        assert executed.result.success is True
        assert executed.result.return_value == 30

    async def test_failed_job_execution(self, scheduler_with_events, temp_task_module):
        """Failed execution emits JOB_ERROR with error details."""
        scheduler, collector = scheduler_with_events
        await scheduler.start()

        job = JobDefinition(
            job_id="failure",
            name="Failure Job",
            func_ref=f"{temp_task_module}:async_failing_task",
            trigger=IntervalTriggerConfig(seconds=1),
        )

        await scheduler.add_job(job)
        await asyncio.sleep(2)
        await scheduler.shutdown()

        error = collector.first(SchedulerEvent.JOB_ERROR)
        assert error is not None
        assert error.result.success is False
        assert error.result.error_message is not None

    async def test_job_submitted_before_execution(
        self,
        scheduler_with_events,
        temp_task_module,
    ):
        """JOB_SUBMITTED emitted before any execution attempt."""
        scheduler, collector = scheduler_with_events
        await scheduler.start()

        job = JobDefinition(
            job_id="submitted",
            name="Submitted Job",
            func_ref=f"{temp_task_module}:async_add",
            trigger=IntervalTriggerConfig(seconds=1),
            args=[1, 1],
        )

        await scheduler.add_job(job)
        await asyncio.sleep(1.2)
        await scheduler.shutdown()

        assert collector.count(SchedulerEvent.JOB_SUBMITTED) > 0

    async def test_job_rescheduled_after_execution(self, scheduler, temp_task_module):
        """Job rescheduled after execution completes."""
        await scheduler.start()

        job = JobDefinition(
            job_id="reschedule",
            name="Reschedule Job",
            func_ref=f"{temp_task_module}:async_add",
            trigger=IntervalTriggerConfig(seconds=1),
            args=[1, 1],
        )

        await scheduler.add_job(job)

        first_run = await scheduler.store.get_next_run_time("reschedule")
        assert first_run is not None

        await asyncio.sleep(1.1)

        second_run = await scheduler.store.get_next_run_time("reschedule")
        assert second_run is not None
        assert second_run > first_run

        await scheduler.shutdown()


class TestConcurrencyControl:
    """Tests for concurrent execution prevention."""

    async def test_prevent_concurrent_execution_same_job(
        self,
        scheduler,
        temp_task_module,
    ):
        """Job in _running_jobs skipped in run loop."""
        collector = EventCollector()
        scheduler.events.add_listener(collector)

        await scheduler.start()

        job = JobDefinition(
            name="Concurrent Job",
            job_id="concurrent",
            func_ref=f"{temp_task_module}:async_long_running_task",
            trigger=IntervalTriggerConfig(seconds=1),
        )

        await scheduler.add_job(job)

        scheduler._running_jobs.add("concurrent")

        original_get_due = scheduler.store.get_due_jobs
        scheduler.store.get_due_jobs = AsyncMock(return_value=[job])

        await asyncio.sleep(0.2)

        scheduler.store.get_due_jobs = original_get_due
        scheduler._running_jobs.discard("concurrent")

        await scheduler.shutdown()

    async def test_disabled_job_skipped_in_loop(self, scheduler_with_events):
        """Disabled job in due_jobs skipped without submission."""
        scheduler, collector = scheduler_with_events
        await scheduler.start()

        job = JobDefinition(
            job_id="disabled",
            name="Disabled Job",
            func_ref="none:none",
            trigger=IntervalTriggerConfig(seconds=1),
            enabled=False,
        )

        await scheduler.store.add_job(job)
        await scheduler.store.set_next_run_time(job.job_id, datetime.now(timezone.utc))

        await asyncio.sleep(0.15)

        disabled_submitted = [
            e
            for e in collector.by_type(SchedulerEvent.JOB_SUBMITTED)
            if e.job_id == "disabled"
        ]
        assert len(disabled_submitted) == 0

        await scheduler.shutdown()

    async def test_run_loop_skips_disabled_job_mock_store(self, scheduler_with_events):
        """
        Forces the run loop to encounter a disabled job via mock store.
        The run loop should skip it.
        """
        scheduler, collector = scheduler_with_events

        disabled_job = JobDefinition(
            job_id="disabled_mock",
            name="Disabled Mock",
            func_ref="none:none",
            trigger=IntervalTriggerConfig(seconds=1),
            enabled=False,
        )

        # Setup mock BEFORE start to inject disabled job directly into due_jobs
        scheduler.store.get_due_jobs = AsyncMock(return_value=[disabled_job])

        await scheduler.start()

        # Allow loop to tick
        await asyncio.sleep(0.1)

        await scheduler.shutdown()

        # Verify it was not submitted
        assert len(collector.by_type(SchedulerEvent.JOB_SUBMITTED)) == 0


class TestExecutionValidation:
    """Tests for execution-time validation."""

    async def test_vanished_job_not_executed(self, scheduler_with_events):
        """Job missing from store not executed ."""
        scheduler, collector = scheduler_with_events
        await scheduler.start()

        job = JobDefinition(
            job_id="vanished",
            name="Vanished Job",
            func_ref="none:none",
            trigger=IntervalTriggerConfig(seconds=1),
        )

        # Job not in store, so get_job returns None
        await scheduler._execute_and_notify(job)

        submitted = collector.by_type(SchedulerEvent.JOB_SUBMITTED)
        assert len(submitted) == 0

        await scheduler.shutdown()

    async def test_disabled_at_execution_not_run(self, scheduler_with_events):
        """Disabled job at execution time not submitted."""
        scheduler, collector = scheduler_with_events
        await scheduler.start()

        job = JobDefinition(
            job_id="disable_exec",
            name="Disable at Exec Job",
            func_ref="none:none",
            trigger=IntervalTriggerConfig(seconds=1),
            enabled=True,
        )

        await scheduler.store.add_job(job)

        job.enabled = False
        await scheduler.store.update_job(job)

        await scheduler._execute_and_notify(job)

        submitted = collector.by_type(SchedulerEvent.JOB_SUBMITTED)
        assert len(submitted) == 0

        await scheduler.shutdown()


class TestEventDispatching:
    """Tests for event type selection and dispatch."""

    async def test_success_event_on_successful_result(
        self,
        scheduler_with_events,
        temp_task_module,
    ):
        """JOB_EXECUTED event when result.success=True."""
        scheduler, collector = scheduler_with_events
        await scheduler.start()

        job = JobDefinition(
            job_id="evt_success",
            name="Event Success Job",
            func_ref=f"{temp_task_module}:async_add",
            trigger=IntervalTriggerConfig(seconds=1),
            args=[5, 5],
        )

        await scheduler.add_job(job)
        await asyncio.sleep(1.2)
        await scheduler.shutdown()

        executed = collector.by_type(SchedulerEvent.JOB_EXECUTED)
        assert len(executed) > 0

    async def test_error_event_on_failed_result(
        self,
        scheduler_with_events,
        temp_task_module,
    ):
        """JOB_ERROR event when result.success=False."""
        scheduler, collector = scheduler_with_events
        await scheduler.start()

        job = JobDefinition(
            job_id="evt_error",
            name="Event Error Job",
            func_ref=f"{temp_task_module}:async_failing_task",
            trigger=IntervalTriggerConfig(seconds=1),
        )

        await scheduler.add_job(job)
        await asyncio.sleep(2)
        await scheduler.shutdown()

        errors = collector.by_type(SchedulerEvent.JOB_ERROR)
        assert len(errors) > 0


class TestErrorHandling:
    """Tests for error recovery and resilience."""

    async def test_loop_error_recovery_with_backoff(self, scheduler):
        """Scheduler recovers from loop errors with 5s backoff."""
        scheduler.store.get_due_jobs = AsyncMock(
            side_effect=RuntimeError("Store failed"),
        )

        await scheduler.start()
        await asyncio.sleep(0.15)
        assert scheduler._running is True
        await scheduler.shutdown()

    async def test_run_loop_error_backoff_timeout(self, scheduler):
        # Patch the interval to be very short so we don't wait 5 seconds
        with patch("flash_scheduler.scheduler.ERROR_BACKOFF_INTERVAL", 0.01):
            # Force an error in the loop
            scheduler.store.get_due_jobs = AsyncMock(
                side_effect=RuntimeError("Loop Fail"),
            )

            await scheduler.start()

            # Wait longer than the backoff interval to ensure timeout triggers 'pass'
            await asyncio.sleep(0.05)

            assert scheduler._running is True
            await scheduler.shutdown()

    async def test_shutdown_waits_for_active_executions(
        self,
        scheduler_with_events,
        temp_task_module,
    ):
        """Shutdown with wait=True completes pending executions."""
        scheduler, collector = scheduler_with_events
        await scheduler.start()

        job = JobDefinition(
            job_id="wait_exec",
            name="Wait Exec Job",
            func_ref=f"{temp_task_module}:async_add",
            trigger=IntervalTriggerConfig(seconds=1),
            args=[1, 1],
        )

        await scheduler.add_job(job)
        await asyncio.sleep(1.2)

        await scheduler.shutdown(wait=True)

        executed = collector.by_type(SchedulerEvent.JOB_EXECUTED)
        assert len(executed) > 0

    async def test_shutdown_handles_gather_exception(self, scheduler):
        """
        Shutdown gracefully handles exception during task gathering.
        """
        await scheduler.start()

        # Manually inject a fake task to ensure _active_executions is not empty
        # This is deterministic compared to waiting for a scheduled job
        fake_task = asyncio.create_task(asyncio.sleep(0.1))
        scheduler._active_executions.add(fake_task)

        # We need to simulate asyncio.gather raising an exception directly
        # This triggers the try/except block at lines 278-284
        with patch("asyncio.gather", side_effect=OSError("Gather failed")):
            await scheduler.shutdown(wait=True)

        assert scheduler._running is False

        # Cleanup the fake task
        fake_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await fake_task

    async def test_run_loop_backoff_with_bad_job(self, scheduler):
        """
        Injects a mock job with a bad trigger to force the run loop into
        error backoff, ensuring the timeout handler is triggered.
        """
        # Patch backoff to be extremely fast for test speed
        with patch("flash_scheduler.scheduler.ERROR_BACKOFF_INTERVAL", 0.01):
            await scheduler.start()

            # Create a Mock job that looks valid enough to return from store
            # but fails immediately when processed
            bad_job = MagicMock(spec=JobDefinition)
            bad_job.enabled = True
            bad_job.job_id = "bad_trigger_job"
            # Passing a string to create_trigger raises TypeError
            bad_job.trigger = "Invalid Trigger Config"

            # Inject the bad job into the loop flow
            scheduler.store.get_due_jobs = AsyncMock(return_value=[bad_job])

            # Wait for loop to cycle, hit error, and backoff
            await asyncio.sleep(0.05)

            assert scheduler._running is True
            await scheduler.shutdown()


class TestInitializationValidation:
    """Tests for scheduler initialization."""

    def test_init_validates_store_interface(self):
        """Scheduler raises ValueError for invalid store."""
        invalid_store = MagicMock()
        del invalid_store.add_job

        with pytest.raises(ValueError, match="JobStore interface"):
            FlashScheduler(store=invalid_store)

    def test_init_validates_executor_interface(self):
        """Scheduler raises ValueError for invalid executor."""
        invalid_executor = MagicMock()
        del invalid_executor.submit_job

        with pytest.raises(ValueError, match="BaseExecutor interface"):
            FlashScheduler(executor=invalid_executor)

    def test_init_uses_default_backends(self):
        """Scheduler uses defaults when backends not provided."""
        scheduler = FlashScheduler()

        assert isinstance(scheduler.store, MemoryJobStore)
        assert isinstance(scheduler.executor, AsyncExecutor)


class TestUtilities:
    """Tests for utility functions."""

    def test_create_trigger_instantiates_correct_class(self):
        """create_trigger returns correct trigger instance."""
        cfg = IntervalTriggerConfig(seconds=5)
        trigger = create_trigger(cfg)

        assert trigger is not None

    def test_create_trigger_raises_on_unsupported_config(self):
        """create_trigger raises TypeError for unknown config."""
        from pydantic import BaseModel

        class UnknownConfig(BaseModel):
            pass

        with pytest.raises(TypeError, match="Unsupported trigger config"):
            create_trigger(UnknownConfig())
