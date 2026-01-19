from datetime import datetime
from ..schemas import JobDefinition
from .base import JobStore


class MemoryJobStore(JobStore):
    """In-memory job store implementation."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobDefinition] = {}
        self._next_run_times: dict[str, datetime | None] = {}
        self._locked: dict[str, bool] = {}

    async def add_job(self, job: JobDefinition) -> None:
        if job.job_id in self._jobs:
            raise ValueError(f"Job '{job.job_id}' already exits")
        self._jobs[job.job_id] = job
        self._next_run_times[job.job_id] = None

    async def get_job(self, job_id: str) -> JobDefinition | None:
        return self._jobs.get(job_id)

    async def get_due_jobs(self, now: datetime) -> list[JobDefinition]:
        due_jobs = []
        for job_id, next_run in self._next_run_times.items():
            if next_run is not None and next_run <= now:
                job = self._jobs.get(job_id)
                if not job:
                    continue
                if job.enabled and not self._locked.get(job_id, False):
                    due_jobs.append(job)
        return due_jobs

    async def update_job(self, job: JobDefinition) -> None:
        if job.job_id not in self._jobs:
            raise ValueError(f"Job '{job.job_id}' not found")
        self._jobs[job.job_id] = job

    async def remove_job(self, job_id: str) -> bool:
        if job_id not in self._jobs:
            return False
        del self._jobs[job_id]
        self._next_run_times.pop(job_id, None)
        self._locked.pop(job_id, None)
        return True

    async def get_all_jobs(self) -> list[JobDefinition]:
        return list(self._jobs.values())

    async def set_next_run_time(self, job_id: str, next_run: datetime | None) -> None:
        if job_id not in self._jobs:
            raise ValueError(f"Job '{job_id}' not found")
        self._next_run_times[job_id] = next_run

    async def get_next_run_time(self, job_id: str) -> datetime | None:
        return self._next_run_times.get(job_id)

    async def acquire_lock(self, job_id: str) -> bool:
        if job_id not in self._jobs:
            return False
        if self._locked.get(job_id, False):
            return False
        self._locked[job_id] = True
        return True

    async def release_lock(self, job_id: str) -> None:
        self._locked[job_id] = False

    async def is_locked(self, job_id: str) -> bool:
        return self._locked.get(job_id, False)

    async def pause_job(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if job:
            self._jobs[job_id] = job.model_copy(update={"enabled": False})
        else:
            raise ValueError(f"Job '{job_id}' not found")

    async def resume_job(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError(f"Job '{job_id}' not found")
        self._jobs[job_id] = job.model_copy(update={"enabled": False})
