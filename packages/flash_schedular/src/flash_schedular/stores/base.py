from ..schemas import JobDefinition
from datetime import datetime
from abc import ABC, abstractmethod


class JobStore(ABC):
    """
    Interface for job storage.
    """

    @abstractmethod
    async def add_job(self, job: JobDefinition) -> None: ...

    @abstractmethod
    async def get_job(self, job_id: str) -> JobDefinition | None: ...

    @abstractmethod
    async def get_due_jobs(self, now: datetime) -> list[JobDefinition]: ...

    @abstractmethod
    async def update_job(self, job: JobDefinition) -> None: ...

    @abstractmethod
    async def remove_job(self, job_id: str) -> bool: ...

    @abstractmethod
    async def get_all_jobs(self) -> list[JobDefinition]: ...

    @abstractmethod
    async def set_next_run_time(
        self, job_id: str, next_run: datetime | None
    ) -> None: ...

    @abstractmethod
    async def get_next_run_time(self, job_id: str) -> datetime | None: ...

    @abstractmethod
    async def acquire_lock(self, job_id: str) -> bool: ...

    @abstractmethod
    async def release_lock(self, job_id: str) -> None: ...

    @abstractmethod
    async def is_locked(self, job_id: str) -> bool: ...

    @abstractmethod
    async def pause_job(self, job_id: str) -> None: ...

    @abstractmethod
    async def resume_job(self, job_id: str) -> None: ...
