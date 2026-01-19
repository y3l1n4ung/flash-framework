import json
from flash_schedular.schemas import JobDefinition
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, AsyncSession
from datetime import datetime
from .base import JobStore
from sqlalchemy import String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""

    pass


class ScheduledJob(Base):
    """SQLAlchemy model for storing scheduled jobs."""

    __tablename__ = "flash_scheduler.scheduled_jobs"

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
    def from_job_definition(cls, job: JobDefinition) -> "ScheduledJob":
        trigger_data = job.trigger.model_dump()
        return ScheduledJob(
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

    def to_job_definition(self):
        pass


class SQLAlchemyJobStore(JobStore):
    """SQLAlchemy-based persistent job store."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._session_factory = None

    async def initialize(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

    def _get_session(self) -> AsyncSession:
        if self._session_factory is not None:
            return self._session_factory()
        raise RuntimeError("Store not initialized. Call initialize() first.")
