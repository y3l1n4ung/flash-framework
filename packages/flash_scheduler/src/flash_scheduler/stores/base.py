from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from flash_scheduler.schemas import JobDefinition


class JobStore(ABC):
    """
    Interface for job storage.

    Any storage backend (Memory, SQL, Redis) must implement these methods.
    """

    @abstractmethod
    async def add_job(self, job: JobDefinition) -> None:
        """Adds a new job to the store."""
        ...

    @abstractmethod
    async def get_job(self, job_id: str) -> JobDefinition | None:
        """Retrieves a specific job by ID."""
        ...

    @abstractmethod
    async def get_due_jobs(self, now: datetime) -> list[JobDefinition]:
        """Returns a list of jobs that are due to run (next_run_time <= now)."""
        ...

    @abstractmethod
    async def update_job(self, job: JobDefinition) -> None:
        """Updates an existing job definition in the store."""
        ...

    @abstractmethod
    async def remove_job(self, job_id: str) -> bool:
        """Removes a job from the store. Returns True if found and removed."""
        ...

    @abstractmethod
    async def get_all_jobs(self) -> list[JobDefinition]:
        """Returns all jobs currently in the store."""
        ...

    @abstractmethod
    async def set_next_run_time(self, job_id: str, next_run: datetime | None) -> None:
        """Updates just the next run time for a specific job."""
        ...

    @abstractmethod
    async def get_next_run_time(self, job_id: str) -> datetime | None:
        """Retrieves the next scheduled run time for a specific job."""
        ...

    @abstractmethod
    async def acquire_lock(self, job_id: str) -> bool:
        """
        Attempts to acquire a lock for a specific job to prevent double execution.
        Returns True if lock acquired, False if already locked.
        """
        ...

    @abstractmethod
    async def release_lock(self, job_id: str) -> None:
        """Releases the lock for a specific job."""
        ...

    @abstractmethod
    async def is_locked(self, job_id: str) -> bool:
        """Checks if a job is currently locked."""
        ...

    @abstractmethod
    async def pause_job(self, job_id: str) -> None:
        """Pauses a job, preventing it from being picked up by get_due_jobs."""
        ...

    @abstractmethod
    async def resume_job(self, job_id: str) -> None:
        """Resumes a paused job."""
        ...
