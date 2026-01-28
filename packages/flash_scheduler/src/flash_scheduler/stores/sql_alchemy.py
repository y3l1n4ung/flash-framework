"""SQLAlchemy-based job store implementation."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import String, Text, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from flash_scheduler.schemas import (
    CalendarIntervalTriggerConfig,
    CronTriggerConfig,
    DateTriggerConfig,
    IntervalTriggerConfig,
    JobDefinition,
    MisfirePolicy,
)

from .base import JobStore


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""


class ScheduledJob(Base):
    """SQLAlchemy model for storing scheduled jobs."""

    __tablename__ = "flash_scheduled_jobs"

    job_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    func_ref: Mapped[str] = mapped_column(String(500))
    trigger_type: Mapped[str] = mapped_column(String(50))
    trigger_data: Mapped[str] = mapped_column(Text)
    args: Mapped[str] = mapped_column(Text)
    kwargs: Mapped[str] = mapped_column(Text)
    max_retries: Mapped[str] = mapped_column(String(10), default="3")
    retry_delay_seconds: Mapped[str] = mapped_column(String(20), default="10")
    timeout_seconds: Mapped[str | None] = mapped_column(String(20), nullable=True)
    misfire_policy: Mapped[str] = mapped_column(String(50), default="RUN_ONCE")
    enabled: Mapped[bool] = mapped_column(default=True)
    next_run_time: Mapped[datetime | None] = mapped_column(nullable=True)
    locked: Mapped[bool] = mapped_column(default=False)
    locked_at: Mapped[datetime | None] = mapped_column(nullable=True)

    @classmethod
    def from_job_definition(cls, job: JobDefinition) -> ScheduledJob:
        """Creates a database model from a Pydantic JobDefinition."""
        trigger_data = job.trigger.model_dump(mode="json")
        return cls(
            job_id=job.job_id,
            name=job.name,
            func_ref=job.func_ref,
            trigger_type=job.trigger.trigger_type,
            trigger_data=json.dumps(trigger_data),
            args=json.dumps(job.args),
            kwargs=json.dumps(job.kwargs),
            max_retries=str(job.max_retries),
            retry_delay_seconds=str(int(job.retry_delay.total_seconds())),
            timeout_seconds=str(int(job.timeout.total_seconds()))
            if job.timeout
            else None,
            misfire_policy=job.misfire_policy.name,
            enabled=job.enabled,
        )

    def to_job_definition(self) -> JobDefinition:
        """Converts this database model back into a Pydantic JobDefinition."""
        trigger_data = json.loads(self.trigger_data)

        if self.trigger_type == "interval":
            trigger = IntervalTriggerConfig(**trigger_data)
        elif self.trigger_type == "cron":
            trigger = CronTriggerConfig(**trigger_data)
        elif self.trigger_type == "date":
            trigger = DateTriggerConfig(**trigger_data)
        elif self.trigger_type == "calendar":
            trigger = CalendarIntervalTriggerConfig(**trigger_data)
        else:
            msg = f"Unknown trigger type: {self.trigger_type}"
            raise ValueError(msg)

        timeout = None
        if self.timeout_seconds:
            timeout = timedelta(seconds=int(self.timeout_seconds))

        return JobDefinition(
            job_id=self.job_id,
            name=self.name,
            func_ref=self.func_ref,
            trigger=trigger,
            args=json.loads(self.args),
            kwargs=json.loads(self.kwargs),
            max_retries=int(self.max_retries),
            retry_delay=timedelta(seconds=int(self.retry_delay_seconds)),
            timeout=timeout,
            misfire_policy=MisfirePolicy[self.misfire_policy],
            enabled=self.enabled,
        )


class SQLAlchemyJobStore(JobStore):
    """
    SQLAlchemy-based persistent job store.

    This store saves job definitions and state to a relational database using
    SQLAlchemy models. It requires an asyncio-compatible engine (e.g., asyncpg,
    aiosqlite).

    Examples:
        >>> from sqlalchemy.ext.asyncio import create_async_engine
        >>> engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        >>> store = SQLAlchemyJobStore(engine)
        >>> await store.initialize()  # Create tables
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._session_factory = None

    async def initialize(self) -> None:
        """
        Creates the necessary database tables if they don't exist.

        Also initializes the session factory. This must be called before
        performing any operations.
        """
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

    def _get_session(self) -> AsyncSession:
        """Helper to create a new async session."""
        if self._session_factory is not None:
            return self._session_factory()
        msg = "Store not initialized. Call initialize() first."
        raise RuntimeError(msg)

    async def add_job(self, job: JobDefinition) -> None:
        """
        Adds a new job to the database.

        Args:
            job: The JobDefinition object to persist.

        Raises:
            ValueError: If a job with the same job_id already exists.
        """
        async with self._get_session() as session:
            existing = await session.get(ScheduledJob, job.job_id)
            if existing:
                msg = f"Job '{job.job_id}' already exists"
                raise ValueError(msg)

            model = ScheduledJob.from_job_definition(job)
            session.add(model)
            await session.commit()

    async def get_job(self, job_id: str) -> JobDefinition | None:
        """
        Retrieves a job by its ID.

        Args:
            job_id: The unique identifier of the job.

        Returns:
            The JobDefinition if found, otherwise None.
        """
        async with self._get_session() as session:
            model = await session.get(ScheduledJob, job_id)
            if model:
                return model.to_job_definition()
            return None

    async def get_due_jobs(self, now: datetime) -> list[JobDefinition]:
        """
        Returns a list of jobs that are due to run.

        A job is considered due if:
        1. next_run_time is set and <= now.
        2. enabled is True.
        3. locked is False.

        Args:
            now: The current datetime (timezone-aware).

        Returns:
            List of JobDefinition objects.
        """
        async with self._get_session() as session:
            stmt = select(ScheduledJob).where(
                ScheduledJob.next_run_time <= now,
                ScheduledJob.next_run_time.isnot(None),
                ScheduledJob.enabled.is_(True),
                ScheduledJob.locked.is_(False),
            )
            result = await session.execute(stmt)
            models = result.scalars().all()
            return [m.to_job_definition() for m in models]

    async def update_job(self, job: JobDefinition) -> None:
        """
        Updates an existing job definition in the database.

        Args:
            job: The updated JobDefinition object.

        Raises:
            ValueError: If the job_id does not exist.
        """
        async with self._get_session() as session:
            model = await session.get(ScheduledJob, job.job_id)
            if not model:
                msg = f"Job '{job.job_id}' not found"
                raise ValueError(msg)

            # Update fields
            model.name = job.name
            model.func_ref = job.func_ref
            model.trigger_type = job.trigger.trigger_type
            model.trigger_data = json.dumps(job.trigger.model_dump())
            model.args = json.dumps(job.args)
            model.kwargs = json.dumps(job.kwargs)
            model.max_retries = str(job.max_retries)
            model.retry_delay_seconds = str(int(job.retry_delay.total_seconds()))
            model.timeout_seconds = (
                str(int(job.timeout.total_seconds())) if job.timeout else None
            )
            model.misfire_policy = job.misfire_policy.name
            model.enabled = job.enabled

            await session.commit()

    async def remove_job(self, job_id: str) -> bool:
        """
        Removes a job from the database.

        Args:
            job_id: The ID of the job to remove.

        Returns:
            True if the job was found and removed, False otherwise.
        """
        async with self._get_session() as session:
            model = await session.get(ScheduledJob, job_id)
            if not model:
                return False

            await session.delete(model)
            await session.commit()
            return True

    async def get_all_jobs(self) -> list[JobDefinition]:
        """
        Returns all stored jobs.

        Returns:
            List of all JobDefinition objects in the database.
        """
        async with self._get_session() as session:
            result = await session.execute(select(ScheduledJob))
            models = result.scalars().all()
            return [m.to_job_definition() for m in models]

    async def set_next_run_time(self, job_id: str, next_run: datetime | None) -> None:
        """
        Updates the next scheduled run time for a job.

        Args:
            job_id: The job ID.
            next_run: The new run time (timezone-aware) or None.

        Raises:
            ValueError: If the job_id is not found.
        """
        async with self._get_session() as session:
            model = await session.get(ScheduledJob, job_id)
            if not model:
                msg = f"Job '{job_id}' not found"
                raise ValueError(msg)

            model.next_run_time = next_run
            await session.commit()

    async def get_next_run_time(self, job_id: str) -> datetime | None:
        """
        Gets the next scheduled run time for a job.

        Args:
            job_id: The job ID.

        Returns:
            The datetime (timezone-aware) or None.
        """
        async with self._get_session() as session:
            model = await session.get(ScheduledJob, job_id)
            if model and model.next_run_time:
                next_run = model.next_run_time
                if next_run.tzinfo is None:
                    # SQLAlchemy might return naive datetime depending on backend
                    next_run = next_run.replace(tzinfo=timezone.utc)
                return next_run
            return None

    async def acquire_lock(self, job_id: str) -> bool:
        """
        Acquires a lock for the job to prevent concurrent execution.

        Args:
            job_id: The job ID to lock.

        Returns:
            True if lock acquired, False if already locked or job missing.
        """
        async with self._get_session() as session:
            model = await session.get(ScheduledJob, job_id)
            if not model:
                return False

            if model.locked:
                return False

            model.locked = True
            model.locked_at = datetime.now(timezone.utc)
            await session.commit()
            return True

    async def release_lock(self, job_id: str) -> None:
        """
        Releases the lock for a job.

        Args:
            job_id: The job ID to unlock.
        """
        async with self._get_session() as session:
            model = await session.get(ScheduledJob, job_id)
            if model:
                model.locked = False
                model.locked_at = None
                await session.commit()

    async def is_locked(self, job_id: str) -> bool:
        """
        Checks if a job is locked.

        Args:
            job_id: The job ID.

        Returns:
            True if locked, False otherwise.
        """
        async with self._get_session() as session:
            model = await session.get(ScheduledJob, job_id)
            if model:
                return model.locked
            return False

    async def pause_job(self, job_id: str) -> None:
        """
        Pauses a job (sets enabled=False).

        Args:
            job_id: The job ID.

        Raises:
            ValueError: If job not found.
        """
        async with self._get_session() as session:
            model = await session.get(ScheduledJob, job_id)
            if not model:
                msg = f"Job '{job_id}' not found"
                raise ValueError(msg)

            model.enabled = False
            await session.commit()

    async def resume_job(self, job_id: str) -> None:
        """
        Resumes a job (sets enabled=True).

        Args:
            job_id: The job ID.

        Raises:
            ValueError: If job not found.
        """
        async with self._get_session() as session:
            model = await session.get(ScheduledJob, job_id)
            if not model:
                msg = f"Job '{job_id}' not found"
                raise ValueError(msg)

            model.enabled = True
            await session.commit()
