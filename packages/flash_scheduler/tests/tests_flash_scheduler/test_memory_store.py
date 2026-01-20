import pytest
from datetime import datetime, timezone
from flash_scheduler.stores.memory import MemoryJobStore
from flash_scheduler.schemas import JobDefinition, IntervalTriggerConfig


@pytest.fixture
def store():
    return MemoryJobStore()


@pytest.fixture
def job():
    trigger = IntervalTriggerConfig(seconds=60)
    return JobDefinition(
        job_id="test_job_1",
        name="Test Job",
        func_ref="my.module:my_func",
        trigger=trigger,
        enabled=True,
    )


@pytest.mark.asyncio
async def test_add_and_get_job(store, job):
    await store.add_job(job)

    retrieved = await store.get_job("test_job_1")
    assert retrieved == job
    assert retrieved.job_id == "test_job_1"
    assert retrieved.func_ref == "my.module:my_func"


@pytest.mark.asyncio
async def test_add_duplicate_job_raises_error(store, job):
    await store.add_job(job)
    with pytest.raises(ValueError, match="already exists"):
        await store.add_job(job)


@pytest.mark.asyncio
async def test_remove_job(store, job):
    await store.add_job(job)
    assert await store.remove_job("test_job_1") is True
    assert await store.get_job("test_job_1") is None
    # Remove non-existent
    assert await store.remove_job("test_job_1") is False


@pytest.mark.asyncio
async def test_get_due_jobs(store, job):
    await store.add_job(job)
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    # 1. No next run time set -> Not due
    assert await store.get_due_jobs(now) == []

    # 2. Next run time in future -> Not due
    future = datetime(2026, 1, 1, 13, 0, tzinfo=timezone.utc)
    await store.set_next_run_time("test_job_1", future)
    assert await store.get_due_jobs(now) == []

    # 3. Next run time in past/now -> Due
    past = datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc)
    await store.set_next_run_time("test_job_1", past)
    due = await store.get_due_jobs(now)
    assert len(due) == 1
    assert due[0].job_id == "test_job_1"


@pytest.mark.asyncio
async def test_due_jobs_excludes_paused_and_locked(store, job):
    await store.add_job(job)
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    past = datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc)
    await store.set_next_run_time("test_job_1", past)

    # Case A: Locked job shouldn't be due
    await store.acquire_lock("test_job_1")
    assert await store.get_due_jobs(now) == []
    await store.release_lock("test_job_1")
    assert len(await store.get_due_jobs(now)) == 1

    # Case B: Paused job shouldn't be due
    await store.pause_job("test_job_1")
    assert await store.get_due_jobs(now) == []

    # Check resume makes it due again
    await store.resume_job("test_job_1")
    assert len(await store.get_due_jobs(now)) == 1


@pytest.mark.asyncio
async def test_update_job(store, job):
    await store.add_job(job)

    # Create an updated version of the job using Pydantic's copy method
    updated_job = job.model_copy(update={"enabled": False})
    await store.update_job(updated_job)

    retrieved = await store.get_job("test_job_1")
    assert retrieved.enabled is False


@pytest.mark.asyncio
async def test_update_non_existent_job_raises_error(store, job):
    with pytest.raises(ValueError, match="not found"):
        await store.update_job(job)


@pytest.mark.asyncio
async def test_locking_mechanisms(store, job):
    await store.add_job(job)

    # Initially unlocked
    assert await store.is_locked("test_job_1") is False

    # Acquire lock
    assert await store.acquire_lock("test_job_1") is True
    assert await store.is_locked("test_job_1") is True

    # Fail to acquire again
    assert await store.acquire_lock("test_job_1") is False

    # Release
    await store.release_lock("test_job_1")
    assert await store.is_locked("test_job_1") is False

    # Acquire non-existent job
    assert await store.acquire_lock("unknown") is False


@pytest.mark.asyncio
async def test_pause_resume(store, job):
    await store.add_job(job)

    # Pause
    await store.pause_job("test_job_1")
    job_paused = await store.get_job("test_job_1")
    assert job_paused.enabled is False

    # Resume
    await store.resume_job("test_job_1")
    job_resumed = await store.get_job("test_job_1")
    assert job_resumed.enabled is True

    # Invalid IDs
    with pytest.raises(ValueError):
        await store.pause_job("unknown")
    with pytest.raises(ValueError):
        await store.resume_job("unknown")


@pytest.mark.asyncio
async def test_get_all_jobs(store, job):
    assert await store.get_all_jobs() == []
    await store.add_job(job)
    all_jobs = await store.get_all_jobs()
    assert len(all_jobs) == 1
    assert all_jobs[0] == job


@pytest.mark.asyncio
async def test_set_next_run_time_error(store):
    with pytest.raises(ValueError, match="not found"):
        await store.set_next_run_time("non_existent", datetime.now())


@pytest.mark.asyncio
async def test_get_next_run_time(store, job):
    await store.add_job(job)
    assert await store.get_next_run_time("test_job_1") is None

    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    await store.set_next_run_time("test_job_1", now)

    assert await store.get_next_run_time("test_job_1") == now

    # Non-existent job
    assert await store.get_next_run_time("unknown") is None


@pytest.mark.asyncio
async def test_get_due_jobs_inconsistency_handling(store):
    """
    Covers the case where a job_id exists in _next_run_times but is missing from _jobs.
    """
    # Manually inject an orphan next_run_time to simulate state corruption
    orphan_id = "orphan_job"
    past = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    store._next_run_times[orphan_id] = past

    # Ensure it's not in the main jobs dict
    assert orphan_id not in store._jobs

    # calling get_due_jobs should safely ignore the orphan without crashing
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    due = await store.get_due_jobs(now)

    assert due == []
