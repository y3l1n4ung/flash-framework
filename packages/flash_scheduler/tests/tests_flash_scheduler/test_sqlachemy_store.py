import pytest
from datetime import datetime, timezone, timedelta
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from flash_scheduler.stores.sql_alchemy import SQLAlchemyJobStore, ScheduledJob
from flash_scheduler.schemas import (
    JobDefinition,
    IntervalTriggerConfig,
    CronTriggerConfig,
    DateTriggerConfig,
    CalendarIntervalTriggerConfig,
)

# Apply asyncio marker to all tests in this module
pytestmark = pytest.mark.asyncio


# --- Fixtures ---


@pytest_asyncio.fixture
async def engine():
    # Use in-memory SQLite for testing
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def store(engine) -> SQLAlchemyJobStore:
    store = SQLAlchemyJobStore(engine)
    await store.initialize()
    return store


@pytest.fixture
def job():
    trigger = IntervalTriggerConfig(seconds=60)
    return JobDefinition(
        job_id="sql_job_1",
        name="SQL Test Job",
        func_ref="my.module:func",
        trigger=trigger,
        enabled=True,
    )


# --- Unit Tests for Model Serialization ---


async def test_scheduled_job_model_serialization_interval_with_timeout():
    """Covers IntervalTrigger deserialization and Timeout logic."""
    trigger = IntervalTriggerConfig(seconds=30)
    timeout = timedelta(seconds=60)
    job = JobDefinition(
        job_id="interval_timeout",
        name="Interval",
        func_ref="m:f",
        trigger=trigger,
        timeout=timeout,
    )

    model = ScheduledJob.from_job_definition(job)
    assert model.timeout_seconds == "60"

    restored = model.to_job_definition()
    assert restored.timeout == timeout
    assert isinstance(restored.trigger, IntervalTriggerConfig)


async def test_scheduled_job_model_serialization_cron():
    """Covers CronTrigger deserialization."""
    trigger = CronTriggerConfig(minute="*")
    job = JobDefinition(job_id="cron", name="C", func_ref="m:f", trigger=trigger)

    model = ScheduledJob.from_job_definition(job)
    restored = model.to_job_definition()
    assert isinstance(restored.trigger, CronTriggerConfig)


async def test_scheduled_job_model_serialization_date():
    """Covers DateTrigger deserialization."""
    run_at = datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc)
    trigger = DateTriggerConfig(run_at=run_at)
    job = JobDefinition(job_id="date", name="D", func_ref="m:f", trigger=trigger)

    model = ScheduledJob.from_job_definition(job)
    restored = model.to_job_definition()
    assert isinstance(restored.trigger, DateTriggerConfig)


async def test_scheduled_job_model_serialization_calendar():
    """Covers CalendarIntervalTrigger deserialization."""
    trigger = CalendarIntervalTriggerConfig(months=1)
    job = JobDefinition(job_id="cal", name="C", func_ref="m:f", trigger=trigger)

    model = ScheduledJob.from_job_definition(job)
    restored = model.to_job_definition()
    assert isinstance(restored.trigger, CalendarIntervalTriggerConfig)


async def test_scheduled_job_model_invalid_trigger_type():
    """Covers invalid trigger type error handling."""
    model = ScheduledJob(
        job_id="bad",
        name="Bad",
        func_ref="m:f",
        trigger_type="unknown_type",
        trigger_data="{}",
        args="[]",
        kwargs="{}",
        max_retries="3",
        retry_delay_seconds="10",
        misfire_policy="RUN_ONCE",
        enabled=True,
    )

    with pytest.raises(ValueError, match="Unknown trigger type"):
        model.to_job_definition()


# --- Integration Tests: Happy Path ---


async def test_init_creates_tables(store):
    assert store._session_factory is not None


async def test_add_and_get_job(store, job):
    await store.add_job(job)

    retrieved = await store.get_job("sql_job_1")
    assert retrieved is not None
    assert retrieved.job_id == "sql_job_1"
    # Verify serialization/deserialization of complex types
    assert retrieved.trigger.trigger_type == "interval"
    assert retrieved.trigger.seconds == 60


async def test_add_duplicate_raises_error(store, job):
    await store.add_job(job)
    with pytest.raises(ValueError, match="already exists"):
        await store.add_job(job)


async def test_update_job(store, job):
    await store.add_job(job)

    # Update name and disable
    updated_job = job.model_copy(update={"name": "Renamed Job", "enabled": False})
    await store.update_job(updated_job)

    retrieved = await store.get_job("sql_job_1")
    assert retrieved.name == "Renamed Job"
    assert retrieved.enabled is False


async def test_remove_job(store, job):
    await store.add_job(job)
    assert await store.remove_job("sql_job_1") is True
    assert await store.get_job("sql_job_1") is None
    # Remove missing
    assert await store.remove_job("missing") is False


async def test_persistence_between_sessions(job):
    """Verify data persists across different store instances (sharing engine)."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    store_a = SQLAlchemyJobStore(engine)
    await store_a.initialize()
    await store_a.add_job(job)

    store_b = SQLAlchemyJobStore(engine)
    await store_b.initialize()
    retrieved = await store_b.get_job("sql_job_1")

    assert retrieved is not None
    assert retrieved.job_id == "sql_job_1"
    await engine.dispose()


async def test_get_due_jobs_filtering(store: SQLAlchemyJobStore, job):
    await store.add_job(job)
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    # Not due yet (next_run_at is None)
    assert await store.get_due_jobs(now) == []

    # Set Due time
    past = datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc)
    await store.set_next_run_time("sql_job_1", past)

    due = await store.get_due_jobs(now)
    assert len(due) == 1

    # Lock it -> Should not be due
    await store.acquire_lock("sql_job_1")
    assert await store.get_due_jobs(now) == []

    # Unlock -> Due again
    await store.release_lock("sql_job_1")
    assert len(await store.get_due_jobs(now)) == 1

    # Disable -> Should not be due
    await store.pause_job("sql_job_1")
    assert await store.get_due_jobs(now) == []


async def test_lock_mechanism(store, job):
    await store.add_job(job)

    assert await store.acquire_lock("sql_job_1") is True
    # Can't lock twice
    assert await store.acquire_lock("sql_job_1") is False
    assert await store.is_locked("sql_job_1") is True

    await store.release_lock("sql_job_1")
    assert await store.is_locked("sql_job_1") is False


async def test_get_all_jobs(store, job):
    await store.add_job(job)
    all_jobs = await store.get_all_jobs()
    assert len(all_jobs) == 1
    assert all_jobs[0].job_id == "sql_job_1"


async def test_set_next_run_at(store: SQLAlchemyJobStore, job):
    await store.add_job(job)
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    await store.set_next_run_time("sql_job_1", now)
    assert await store.get_next_run_time("sql_job_1") == now


async def test_pause_resume_state_transitions(store, job):
    """Verifies that resume_job correctly sets enabled=True."""
    await store.add_job(job)

    # Pause
    await store.pause_job("sql_job_1")
    assert (await store.get_job("sql_job_1")).enabled is False

    # Resume (Hits model.enabled = True)
    await store.resume_job("sql_job_1")
    assert (await store.get_job("sql_job_1")).enabled is True


# --- Integration Tests: Error Paths & Edge Cases (Critical for Coverage) ---


async def test_get_job_not_found(store):
    """Should return None if the job is missing."""
    assert await store.get_job("missing") is None


async def test_update_job_not_found(store, job):
    job_missing = job.model_copy(update={"job_id": "missing"})
    with pytest.raises(ValueError, match="not found"):
        await store.update_job(job_missing)


async def test_set_next_run_at_not_found(store):
    with pytest.raises(ValueError, match="not found"):
        await store.set_next_run_time("missing", datetime.now())


async def test_pause_resume_not_found(store):
    """Ensure error is raised if pausing/resuming a non-existent job."""
    with pytest.raises(ValueError, match="not found"):
        await store.pause_job("missing")
    with pytest.raises(ValueError, match="not found"):
        await store.resume_job("missing")


async def test_get_next_run_at_logic(store: SQLAlchemyJobStore, job):
    """Ensure next_run_at retrieval handles default None and missing jobs."""
    await store.add_job(job)
    # Default is None
    assert await store.get_next_run_time("sql_job_1") is None
    # Missing is None
    assert await store.get_next_run_time("missing") is None

    # Set and Retrieve
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    await store.set_next_run_time("sql_job_1", now)
    assert await store.get_next_run_time("sql_job_1") == now


async def test_get_next_run_at_naive_handling(store, job):
    """
    Explicitly covers naive datetime handling.
    Some DB drivers return naive datetimes; this ensures we coerce them to UTC.
    """
    await store.add_job(job)

    # Force a naive datetime into the store (simulating driver behavior)
    naive_dt = datetime(2026, 1, 1, 12, 0)
    await store.set_next_run_time("sql_job_1", naive_dt)

    retrieved = await store.get_next_run_time("sql_job_1")
    assert retrieved is not None
    # Must be timezone aware now
    assert retrieved.tzinfo is not None
    assert retrieved.replace(tzinfo=None) == naive_dt


async def test_acquire_lock_not_found(store):
    """Should return False if trying to lock a missing job."""
    assert await store.acquire_lock("missing") is False


async def test_is_locked_not_found(store):
    """Should return False if checking lock on a missing job."""
    assert await store.is_locked("missing") is False


async def test_uninitialized_store_raises_error(engine):
    """Covers RuntimeError when store is not initialized."""
    store = SQLAlchemyJobStore(engine)
    # We deliberately do NOT call await store.initialize()

    with pytest.raises(RuntimeError, match="Store not initialized"):
        await store.get_all_jobs()
