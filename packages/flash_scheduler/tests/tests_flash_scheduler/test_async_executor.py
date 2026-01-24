import asyncio
import sys
from datetime import timedelta
from unittest.mock import patch

import pytest
from flash_scheduler.executors.async_executor import AsyncExecutor
from flash_scheduler.schemas import IntervalTriggerConfig, JobDefinition

# Apply asyncio marker to all tests in this module
pytestmark = pytest.mark.asyncio


@pytest.fixture
def executor():
    return AsyncExecutor()


@pytest.fixture
def base_job(temp_task_module):
    trigger = IntervalTriggerConfig(seconds=60)
    return JobDefinition(
        job_id="test_job",
        name="Test",
        # Use the dynamic module name found on disk
        func_ref=f"{temp_task_module}:async_success_task",
        trigger=trigger,
        enabled=True,
    )


async def test_executor_lifecycle(executor):
    """Test start and shutdown state transitions."""
    assert executor._running is False

    await executor.start()
    assert executor._running is True

    await executor.shutdown()
    assert executor._running is False


async def test_submit_without_start_raises_error(executor, base_job):
    """Ensure jobs cannot be submitted to a stopped executor."""
    with pytest.raises(RuntimeError, match="not running"):
        await executor.submit_job(base_job)


async def test_execute_async_success(executor, base_job, temp_task_module):
    """Test successful execution of an async function."""
    await executor.start()

    # Point to the real file created in tmp_path
    base_job.func_ref = f"{temp_task_module}:async_success_task"
    base_job.args = [10, 20]

    result = await executor.submit_job(base_job)

    assert result.success is True
    assert result.return_value == 30
    assert result.job_id == base_job.job_id
    assert result.error_message is None
    assert result.duration >= timedelta(seconds=0)


async def test_execute_sync_success(executor, base_job, temp_task_module):
    """Test successful execution of a sync function (via thread pool)."""
    await executor.start()

    base_job.func_ref = f"{temp_task_module}:sync_success_task"
    base_job.args = [5, 5]

    result = await executor.submit_job(base_job)

    assert result.success is True
    assert result.return_value == 25


async def test_execute_handle_exception_async(executor, base_job, temp_task_module):
    """Test error handling for async functions."""
    await executor.start()

    base_job.func_ref = f"{temp_task_module}:async_failing_task"

    result = await executor.submit_job(base_job)

    assert result.success is False
    assert result.return_value is None
    assert "Oops async" in result.error_message
    assert result.error_traceback is not None


async def test_execute_handle_exception_sync(executor, base_job, temp_task_module):
    """Test error handling for sync functions."""
    await executor.start()

    base_job.func_ref = f"{temp_task_module}:sync_failing_task"

    result = await executor.submit_job(base_job)

    assert result.success is False
    assert "Oops sync" in result.error_message


async def test_execute_import_error_module(executor, base_job):
    """Test handling of missing modules."""
    await executor.start()

    base_job.func_ref = "non_existent_module:func"

    result = await executor.submit_job(base_job)

    assert result.success is False
    assert "No module named" in result.error_message


async def test_execute_import_error_function(executor, base_job, temp_task_module):
    """Test handling of missing functions within existing modules."""
    await executor.start()

    # This module exists (on disk), but 'missing_func' does not
    base_job.func_ref = f"{temp_task_module}:missing_func"

    result = await executor.submit_job(base_job)

    assert result.success is False
    # Fixed assertion: Matches "module ... has no attribute 'missing_func'"
    assert "has no attribute 'missing_func'" in result.error_message


async def test_shutdown_waits_for_tasks(executor, base_job, temp_task_module):
    """Test that shutdown(wait=True) waits for pending tasks."""
    await executor.start()

    # async_success_task sleeps 0.01s, long enough to be pending
    base_job.func_ref = f"{temp_task_module}:async_success_task"
    base_job.args = [1, 1]

    task = asyncio.create_task(executor.submit_job(base_job))

    # Give it a tiny moment to start running
    await asyncio.sleep(0.001)

    # Should block until the task finishes
    await executor.shutdown(wait=True)

    result = await task
    assert result.success is True


async def test_start_no_event_loop(executor):
    """RuntimeError if started without loop."""
    with patch("asyncio.get_running_loop", side_effect=RuntimeError):
        with pytest.raises(
            RuntimeError, match="must be started inside a running event loop"
        ):
            await executor.start()


async def test_shutdown_nowait_cancels_tasks(executor, base_job, temp_task_module):
    await executor.start()

    # Use a task that runs long enough to actually need cancelling
    base_job.func_ref = f"{temp_task_module}:async_long_running_task"
    base_job.args = []  # Ensure arguments are clear for this no-arg task

    # Launch job in background
    task = asyncio.create_task(executor.submit_job(base_job))

    # Yield to allow task to start
    await asyncio.sleep(0.001)

    # Shutdown immediately, forcing cancellation
    await executor.shutdown(wait=False)

    # The task wrapper propagates cancellation
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_cached_import_coverage(executor, temp_task_module):
    """Covers the case where the module is already in sys.modules."""
    await executor.start()

    # Ensure the module is in sys.modules (the fixture does this, but we'll be explicit)
    import importlib

    importlib.import_module(temp_task_module)
    assert temp_task_module in sys.modules

    trigger = IntervalTriggerConfig(seconds=60)
    job = JobDefinition(
        job_id="cached_job",
        name="Cached",
        func_ref=f"{temp_task_module}:sync_success_task",
        trigger=trigger,
        args=[2, 3],
    )

    result = await executor.submit_job(job)
    assert result.success is True
    assert result.return_value == 6


async def test_dynamic_import(executor, tmp_path):
    await executor.start()

    # 1. Create a fresh package structure in tmp_path
    pkg_dir = tmp_path / "dynamic_test_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").touch()
    (pkg_dir / "worker.py").write_text(
        "def run_me(): return 'dynamic_ok'", encoding="utf-8"
    )

    # 2. Add to sys.path so importlib can find it
    sys.path.insert(0, str(tmp_path))

    try:
        # Define job pointing to this new file
        trigger = IntervalTriggerConfig(seconds=60)
        job = JobDefinition(
            job_id="dyn_job",
            name="Dyn",
            func_ref="dynamic_test_pkg.worker:run_me",
            trigger=trigger,
        )

        # Ensure it's strictly NOT in sys.modules
        if "dynamic_test_pkg.worker" in sys.modules:
            del sys.modules["dynamic_test_pkg.worker"]

        # 3. Submit
        result = await executor.submit_job(job)

        assert result.success is True
        assert result.return_value == "dynamic_ok"

        # Verify it was indeed imported
        assert "dynamic_test_pkg.worker" in sys.modules

    finally:
        # Cleanup path
        sys.path.remove(str(tmp_path))
