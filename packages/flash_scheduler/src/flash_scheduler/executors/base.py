"""Abstract base class for job executors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from flash_scheduler.schemas import JobDefinition


class BaseExecutor(ABC):
    """
    Interface for classes that execute jobs.

    Executors are responsible for:
    1. Taking a JobDefinition.
    2. Loading the actual python function.
    3. Running it (potentially in a separate thread/process).
    4. Returning/Handling the result.

    Examples:
        >>> # Subclassing BaseExecutor
        >>> class MyExecutor(BaseExecutor):
        ...     async def start(self): pass
        ...     async def shutdown(self, wait=True): pass
        ...     async def submit_job(self, job): return "Result"
    """

    @abstractmethod
    async def start(self) -> None:
        """Initialize any resources (pools, loops)."""
        ...

    @abstractmethod
    async def shutdown(self, wait: bool = True) -> None:
        """
        Shutdown the executor.

        Args:
            wait: If True, wait for currently running jobs to finish.
        """
        ...

    @abstractmethod
    async def submit_job(self, job: JobDefinition) -> Any:
        """
        Submit a job for execution.

        This method should verify the function exists and schedule it
        to run immediately.
        """
        ...
