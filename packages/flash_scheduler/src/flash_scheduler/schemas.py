"""Pydantic schemas/data contracts for the scheduler."""

import zoneinfo
from datetime import datetime, timedelta, timezone
from enum import Enum, auto
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

from pydantic import (
    BaseModel,
    BeforeValidator,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)


def validate_timezone(v: Any) -> Any:
    """Ensure the value is a valid timezone or ZoneInfo object."""
    if isinstance(v, (timezone, zoneinfo.ZoneInfo)):
        return v
    if isinstance(v, str):
        try:
            return zoneinfo.ZoneInfo(v)
        except zoneinfo.ZoneInfoNotFoundError as z:
            msg = f"Invalid timezone name: {v}"
            raise ValueError(msg) from z
    msg = f"Invalid timezone type: {type(v).__name__}"
    raise ValueError(msg)


# Annotated type to handle timezone validation explicitly.
# We use Any here because Pydantic V2 cannot generate a core schema for the
# datetime.timezone class specifically. The BeforeValidator handles the actual
# type enforcement and conversion.
TzType = Annotated[Any, BeforeValidator(validate_timezone)]


class MisfirePolicy(Enum):
    """Policy for handling misfired jobs."""

    RUN_ONCE = auto()
    SKIP = auto()
    RUN_ALL = auto()


class JobStatus(Enum):
    """Job execution status."""

    PENDING = auto()
    RUNNING = auto()
    SUCCEEDED = auto()
    FAILED = auto()
    HALTED = auto()


class IntervalTriggerConfig(BaseModel):
    """Configuration for interval-based triggers."""

    trigger_type: Literal["interval"] = "interval"
    weeks: int = 0
    days: int = 0
    hours: int = 0
    minutes: int = 0
    seconds: int = 0
    start_time: datetime | None = None
    end_time: datetime | None = None
    jitter: int | None = None
    interval: timedelta | None = None

    @model_validator(mode="after")
    def validate_interval(self) -> "IntervalTriggerConfig":
        total = timedelta(
            weeks=self.weeks,
            days=self.days,
            hours=self.hours,
            minutes=self.minutes,
            seconds=self.seconds,
        )
        if total <= timedelta(0):
            msg = "interval must be positive"
            raise ValueError(msg)
        return self


class CronTriggerConfig(BaseModel):
    """Configuration for cron-based triggers.

    Supports 6-field cron expressions: second minute hour day month day_of_week

    Aliases:
        - Days: SUN, MON, TUE, WED, THU, FRI, SAT
        - Months: JAN, FEB, MAR, APR, MAY, JUN, JUL, AUG, SEP, OCT, NOV, DEC

    Examples:
        - second="0", minute="*/15" - Every 15 minutes at :00
        - second="30", minute="0", hour="9", day_of_week="MON-FRI" - 9:00:30 AM weekdays
        - month="JAN,JUL", day="1" - First day of January and July
    """

    trigger_type: Literal["cron"] = "cron"
    second: str = "0"
    minute: str = "*"
    hour: str = "*"
    day: str = "*"
    month: str = "*"
    day_of_week: str = "*"
    tz: TzType | None = ZoneInfo("UTC")
    jitter: int | None = None

    @field_serializer("tz")
    def serialize_timezone(self, v: Any) -> str | None:
        """Convert ZoneInfo or timezone object to string for JSON serialization."""
        if isinstance(v, zoneinfo.ZoneInfo):
            return v.key
        if isinstance(v, timezone):
            return str(v)
        if v is None:
            return None
        msg = f"Expected str, ZoneInfo, or timezone, got {type(v).__name__}"
        raise ValueError(msg)


class DateTriggerConfig(BaseModel):
    """Configuration for one-time date triggers."""

    trigger_type: Literal["date"] = "date"
    run_at: datetime

    @field_validator("run_at")
    @classmethod
    def validate_timezone(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            msg = "run_at must be timezone-aware"
            raise ValueError(msg)
        return v


class CalendarIntervalTriggerConfig(BaseModel):
    """Configuration for calendar-aware interval triggers.

    Unlike IntervalTriggerConfig, this respects calendar boundaries
    (e.g., months/years of varying lengths).

    Examples:
        - months=1: Every month on the same day
        - months=3, hour=9: Every quarter at 9:00 AM
        - years=1: Every year on the anniversary
    """

    trigger_type: Literal["calendar"] = "calendar"
    years: int = 0
    months: int = 0
    weeks: int = 0
    days: int = 0
    hour: int = 0
    minute: int = 0
    second: int = 0
    start_time: datetime | None = None
    end_time: datetime | None = None
    tz: TzType | None = None
    jitter: int | None = None

    @field_serializer("tz")
    def serialize_timezone(self, v: Any) -> str | None:
        """Convert ZoneInfo or timezone object to string for JSON serialization."""
        if isinstance(v, zoneinfo.ZoneInfo):
            return v.key
        if isinstance(v, timezone):
            # Handles fixed offset timezones like UTC
            return str(v)
        if v is None:
            return None
        msg = f"Expected str, ZoneInfo, or timezone, got {type(v).__name__}"
        raise ValueError(msg)

    @model_validator(mode="after")
    def validate_interval(self) -> "CalendarIntervalTriggerConfig":
        if self.years == 0 and self.months == 0 and self.weeks == 0 and self.days == 0:
            msg = "At least one of years, months, weeks, or days must be specified"
            raise ValueError(
                msg,
            )
        return self


TriggerConfig = (
    IntervalTriggerConfig
    | CronTriggerConfig
    | DateTriggerConfig
    | CalendarIntervalTriggerConfig
)


class JobDefinition(BaseModel):
    """Complete definition of a scheduled job."""

    job_id: str
    name: str
    func_ref: str
    trigger: TriggerConfig
    args: list[Any] = Field(default_factory=list)
    kwargs: dict[str, Any] = Field(default_factory=dict)
    max_retries: int = 3
    retry_delay: timedelta = Field(default=timedelta(seconds=10))
    timeout: timedelta | None = None
    misfire_policy: MisfirePolicy = MisfirePolicy.RUN_ONCE
    max_instances: int = 1
    enabled: bool = True
    coalesce: bool = True

    @field_validator("func_ref")
    @classmethod
    def validate_func_ref(cls, v: str) -> str:
        if ":" not in v:
            msg = "func_ref must be in format 'module.path:function_name'"
            raise ValueError(msg)
        return v


class ExecutionResult(BaseModel):
    """Result of a job execution."""

    job_id: str
    success: bool
    started_at: datetime
    finished_at: datetime
    return_value: Any = None
    error_message: str | None = None
    error_traceback: str | None = None

    @property
    def duration(self) -> timedelta:
        return self.finished_at - self.started_at


class SchedulerConfig(BaseModel):
    """Configuration for the scheduler engine."""

    tick_interval: timedelta = Field(default=timedelta(seconds=1))
    misfire_grace_period: timedelta = Field(default=timedelta(minutes=1))
    max_concurrent_jobs: int = 10
    default_max_retries: int = 3
    default_retry_delay: timedelta = Field(default=timedelta(seconds=10))
