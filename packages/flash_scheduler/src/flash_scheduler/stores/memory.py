from __future__ import annotations

from datetime import datetime

from ..schemas import JobDefinition
from .base import JobStore


class MemoryJobStore(JobStore):
    """
    In-memory job store implementation.

    This store keeps all jobs in a Python dictionary. It is not persistent
    and data will be lost when the application stops. Useful for testing
    or simple, ephemeral applications.

    Examples:
        >>> store = MemoryJobStore()
        >>> # Assuming 'job' is a valid JobDefinition
        >>> await store.add_job(job)
        >>> retrieved = await store.get_job("my_job_id")
    """

    def __init__(self) -> None:
        self._jobs: dict[str, JobDefinition] = {}
        self._next_run_times: dict[str, datetime | None] = {}
        self._locked: dict[str, bool] = {}

    async def add_job(self, job: JobDefinition) -> None:
        """
        Adds a new job to the store.

        Args:
            job: The JobDefinition object to store.

        Raises:
            ValueError: If a job with the same job_id already exists.
        """
        if job.job_id in self._jobs:
            raise ValueError(f"Job '{job.job_id}' already exists")
        self._jobs[job.job_id] = job
        self._next_run_times[job.job_id] = None

    async def get_job(self, job_id: str) -> JobDefinition | None:
        """
        Retrieves a job by its ID.

        Args:
            job_id: The unique identifier of the job.

        Returns:
            The JobDefinition if found, otherwise None.
        """
        return self._jobs.get(job_id)

    async def get_due_jobs(self, now: datetime) -> list[JobDefinition]:
        """
        Returns a list of jobs that are due to run.

        A job is considered due if:
        1. It has a scheduled next_run_time that is <= now.
        2. It is 'enabled'.
        3. It is not currently locked by another worker.

        Args:
            now: The current datetime (timezone-aware) to compare against.

        Returns:
            List of JobDefinition objects ready for execution.
        """
        due_jobs = []
        for job_id, next_run in self._next_run_times.items():
            if next_run is not None and next_run <= now:
                job = self._jobs.get(job_id)
                if not job:
                    continue
                # Only return if enabled and not locked
                if job.enabled and not self._locked.get(job_id, False):
                    due_jobs.append(job)
        return due_jobs

    async def update_job(self, job: JobDefinition) -> None:
        """
        Updates an existing job definition.

        Args:
            job: The updated JobDefinition object (must have same job_id).

        Raises:
            ValueError: If the job_id does not exist in the store.
        """
        if job.job_id not in self._jobs:
            raise ValueError(f"Job '{job.job_id}' not found")
        self._jobs[job.job_id] = job

    async def remove_job(self, job_id: str) -> bool:
        """
        Removes a job from the store.

        Args:
            job_id: The unique identifier of the job to remove.

        Returns:
            True if the job was found and removed, False otherwise.
        """
        if job_id not in self._jobs:
            return False
        del self._jobs[job_id]
        self._next_run_times.pop(job_id, None)
        self._locked.pop(job_id, None)
        return True

    async def get_all_jobs(self) -> list[JobDefinition]:
        """
        Returns all stored jobs.

        Returns:
            A list containing every JobDefinition in the store.
        """
        return list(self._jobs.values())

    async def set_next_run_time(self, job_id: str, next_run: datetime | None) -> None:
        """
        Updates the next scheduled run time for a job.

        Args:
            job_id: The job to update.
            next_run: The new next run time, or None if no run is scheduled.

        Raises:
            ValueError: If the job_id does not exist.
        """
        if job_id not in self._jobs:
            raise ValueError(f"Job '{job_id}' not found")
        self._next_run_times[job_id] = next_run

    async def get_next_run_time(self, job_id: str) -> datetime | None:
        """
        Gets the next scheduled run time for a job.

        Args:
            job_id: The job ID to check.

        Returns:
            The datetime of the next run, or None if not scheduled/found.
        """
        return self._next_run_times.get(job_id)

    async def acquire_lock(self, job_id: str) -> bool:
        """
        Attempts to acquire an execution lock for a job.

        Args:
            job_id: The job ID to lock.

        Returns:
            True if the lock was acquired, False if it was already locked or missing.
        """
        if job_id not in self._jobs:
            return False
        if self._locked.get(job_id, False):
            return False
        self._locked[job_id] = True
        return True

    async def release_lock(self, job_id: str) -> None:
        """
        Releases the execution lock for a job.

        Args:
            job_id: The job ID to unlock.
        """
        self._locked[job_id] = False

    async def is_locked(self, job_id: str) -> bool:
        """
        Checks if a job is currently locked.

        Args:
            job_id: The job ID to check.

        Returns:
            True if locked, False otherwise.
        """
        return self._locked.get(job_id, False)

    async def pause_job(self, job_id: str) -> None:
        """
        Pauses a job by setting its 'enabled' status to False.

        Args:
            job_id: The job to pause.

        Raises:
            ValueError: If the job_id does not exist.
        """
        job = self._jobs.get(job_id)
        if job:
            self._jobs[job_id] = job.model_copy(update={"enabled": False})
        else:
            raise ValueError(f"Job '{job_id}' not found")

    async def resume_job(self, job_id: str) -> None:
        """
        Resumes a job by setting its 'enabled' status to True.

        Args:
            job_id: The job to resume.

        Raises:
            ValueError: If the job_id does not exist.
        """
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError(f"Job '{job_id}' not found")
        self._jobs[job_id] = job.model_copy(update={"enabled": True})
