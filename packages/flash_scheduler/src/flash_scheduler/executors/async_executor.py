"""Standard Asyncio Executor."""

from __future__ import annotations

import asyncio
import importlib
import logging
import sys
import traceback
from datetime import datetime, timezone

from flash_scheduler.schemas import ExecutionResult, JobDefinition

from .base import BaseExecutor

logger = logging.getLogger(__name__)


class AsyncExecutor(BaseExecutor):
    """
    Executor that runs jobs in the current event loop.

    Supports:
    - Async functions (awaited directly)
    - Sync functions (run in thread pool to avoid blocking loop)

    Examples:
        >>> executor = AsyncExecutor()
        >>> await executor.start()
        >>> # Assuming 'job' defines an async function
        >>> result = await executor.submit_job(job)
        >>> await executor.shutdown()
    """

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task] = set()
        self._running = False

    async def start(self) -> None:
        """
        Initialize the executor.

        Ensures an event loop is available and marks the executor as active.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError as r:
            msg = "AsyncExecutor must be started inside a running event loop."
            raise RuntimeError(
                msg,
            ) from r
        self._running = True

    async def shutdown(self, *, wait: bool = True) -> None:
        self._running = False
        if wait and self._tasks:
            # Wait for pending tasks
            await asyncio.gather(*self._tasks, return_exceptions=True)
        else:
            # Cancel running tasks
            for task in self._tasks:
                task.cancel()

    async def submit_job(self, job: JobDefinition) -> ExecutionResult:
        """
        Runs the job immediately and returns the result.
        """
        if not self._running:
            msg = "Executor is not running."
            raise RuntimeError(msg)

        task = asyncio.create_task(self._execute_wrapper(job))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

        return await task

    async def _execute_wrapper(self, job: JobDefinition) -> ExecutionResult:
        """Internal wrapper to handle dynamic loading and error catching."""
        start_time = datetime.now(timezone.utc)
        success = False
        return_value = None
        error_msg = None
        error_tb = None

        try:
            # 1. Parse module:func
            module_name, func_name = job.func_ref.split(":")

            # 2. Import module dynamically
            if module_name not in sys.modules:
                module = importlib.import_module(module_name)
            else:
                module = sys.modules[module_name]

            # 3. Get function
            func = getattr(module, func_name)

            # 4. Execute
            if asyncio.iscoroutinefunction(func):
                return_value = await func(*job.args, **job.kwargs)
            else:
                # Run sync functions in thread pool
                return_value = await asyncio.to_thread(func, *job.args, **job.kwargs)

            success = True

        except Exception as e:
            error_msg = str(e)
            error_tb = traceback.format_exc()
            logger.exception("Job %s failed: %s", job.job_id, error_msg)

        finished_at = datetime.now(timezone.utc)

        return ExecutionResult(
            job_id=job.job_id,
            success=success,
            started_at=start_time,
            finished_at=finished_at,
            return_value=return_value,
            error_message=error_msg,
            error_traceback=error_tb,
        )
