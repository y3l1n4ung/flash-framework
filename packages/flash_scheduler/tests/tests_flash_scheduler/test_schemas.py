from zoneinfo import ZoneInfo
import pytest
from datetime import datetime, timedelta, timezone
from pydantic import ValidationError
from flash_scheduler.schemas import (
    IntervalTriggerConfig,
    DateTriggerConfig,
    CalendarIntervalTriggerConfig,
    JobDefinition,
    ExecutionResult,
    CronTriggerConfig,
    MisfirePolicy,
)


def test_interval_config_valid():
    """Should accept valid positive intervals."""
    config = IntervalTriggerConfig(seconds=30)
    assert config.seconds == 30

    config = IntervalTriggerConfig(weeks=1, hours=12)
    assert config.weeks == 1
    assert config.hours == 12


def test_interval_config_invalid_zero():
    """Should raise ValueError if total duration is 0 or negative."""
    with pytest.raises(ValidationError) as exc:
        IntervalTriggerConfig(seconds=0, minutes=0)
    assert "interval must be positive" in str(exc.value)


def test_cron_config_defaults():
    """Should have correct defaults."""
    config = CronTriggerConfig()
    assert config.trigger_type == "cron"
    assert config.second == "0"
    assert config.minute == "*"
    assert config.hour == "*"
    assert config.day == "*"
    assert config.month == "*"
    assert config.day_of_week == "*"
    assert config.tz == ZoneInfo("UTC")


def test_cron_config_custom():
    """Should accept custom values."""
    config = CronTriggerConfig(
        minute="*/15", hour="9-17", day_of_week="MON-FRI", tz=ZoneInfo("US/Eastern")
    )
    assert config.minute == "*/15"
    assert config.hour == "9-17"
    assert config.day_of_week == "MON-FRI"
    assert config.tz == ZoneInfo("US/Eastern")


def test_date_config_valid():
    """Should accept timezone-aware datetimes."""
    dt = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    config = DateTriggerConfig(run_at=dt)
    assert config.run_at == dt


def test_date_config_invalid_naive():
    """Should raise ValueError for naive datetimes."""
    naive_dt = datetime(2026, 1, 1, 12, 0)
    with pytest.raises(ValidationError) as exc:
        DateTriggerConfig(run_at=naive_dt)
    assert "run_at must be timezone-aware" in str(exc.value)


def test_calendar_config_valid():
    """Should accept valid calendar intervals."""
    config = CalendarIntervalTriggerConfig(months=1)
    assert config.months == 1


def test_calendar_config_invalid_empty():
    """Should raise error if no interval components are provided."""
    with pytest.raises(ValidationError) as exc:
        CalendarIntervalTriggerConfig(hour=9)  # Only time, no interval
    assert "At least one of years, months, weeks, or days must be specified" in str(
        exc.value
    )


def test_job_definition_func_ref_valid():
    """Should accept 'module:func' format."""
    trigger = IntervalTriggerConfig(seconds=60)
    job = JobDefinition(
        job_id="1", name="Test", func_ref="my_module.sub:my_func", trigger=trigger
    )
    assert job.func_ref == "my_module.sub:my_func"


def test_job_definition_func_ref_invalid():
    """Should validate func_ref format."""
    trigger = IntervalTriggerConfig(seconds=60)

    # Missing colon
    with pytest.raises(ValidationError) as exc:
        JobDefinition(
            job_id="1", name="Test", func_ref="my_module.my_func", trigger=trigger
        )
    assert "func_ref must be in format" in str(exc.value)


def test_job_definition_defaults():
    """Check default values."""
    trigger = IntervalTriggerConfig(seconds=60)
    job = JobDefinition(job_id="1", name="Test", func_ref="mod:func", trigger=trigger)

    assert job.max_retries == 3
    assert job.retry_delay == timedelta(seconds=10)
    assert job.misfire_policy == MisfirePolicy.RUN_ONCE
    assert job.enabled is True


def test_execution_result_duration():
    """Should correctly calculate duration property."""
    start = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 1, 1, 12, 0, 5, tzinfo=timezone.utc)

    result = ExecutionResult(
        job_id="1", success=True, started_at=start, finished_at=end
    )

    assert result.duration == timedelta(seconds=5)
    assert result.duration.total_seconds() == 5.0


def test_timezone_validation_strings():
    """Should handle string inputs for timezones correctly (lines 28, 30)."""
    # Test valid string
    config = CronTriggerConfig(tz="America/New_York")
    assert isinstance(config.tz, ZoneInfo)
    assert config.tz.key == "America/New_York"

    # Test invalid string
    with pytest.raises(ValidationError) as exc:
        CronTriggerConfig(tz="Invalid/Timezone")
    assert "Invalid timezone name" in str(exc.value)


def test_cron_serialization():
    """Should serialize ZoneInfo and timezone objects correctly (lines 116-118)."""
    # Test ZoneInfo serialization
    config_zi = CronTriggerConfig(tz=ZoneInfo("Asia/Tokyo"))
    dump_zi = config_zi.model_dump()
    assert dump_zi["tz"] == "Asia/Tokyo"

    # Test timezone serialization
    config_tz = CronTriggerConfig(tz=timezone.utc)
    dump_tz = config_tz.model_dump()
    assert dump_tz["tz"] == "UTC"


def test_calendar_serialization():
    """Should serialize ZoneInfo and timezone objects correctly (lines 164, 167)."""
    # Test ZoneInfo serialization
    config_zi = CalendarIntervalTriggerConfig(months=1, tz=ZoneInfo("Europe/London"))
    dump_zi = config_zi.model_dump()
    assert dump_zi["tz"] == "Europe/London"

    # Test timezone serialization
    config_tz = CalendarIntervalTriggerConfig(months=1, tz=timezone.utc)
    dump_tz = config_tz.model_dump()
    assert dump_tz["tz"] == "UTC"


def test_timezone_validation_none():
    """Should explicitly allow None (and hit the serialize fallback)."""
    # This hits the 'if v is None: return None' path
    config = CronTriggerConfig(tz=None)
    assert config.tz is None

    # This hits the 'return v' fallback in serialize_timezone (line 117)
    dump = config.model_dump()
    assert dump["tz"] is None


def test_timezone_validation_invalid_type():
    """Should raise error for non-timezone types (e.g., integers)."""
    # This hits the new 'raise ValueError' path for invalid types
    with pytest.raises(ValidationError) as exc:
        CronTriggerConfig(tz=12345)
    assert "Invalid timezone type: int" in str(exc.value)


def test_timezone_none_handling():
    """Tests the None path in both validator and serializer."""
    # 1. Test Validator (None passes through)
    config = CronTriggerConfig(tz=None)
    assert config.tz is None

    # 2. Test Serializer (None returns None)
    # This hits the 'if v is None' branch in the serializer
    data = config.model_dump()
    assert data["tz"] is None


def test_timezone_validation_error():
    """Tests the final raise in the validator."""
    with pytest.raises(ValidationError):
        # Pass an unsupported type like a list
        CronTriggerConfig(tz=[1, 2, 3])


def test_serializer_raise_fallback():
    """Forces the serializer to hit the final raise for coverage."""
    # 1. Create a valid config
    config = CronTriggerConfig(tz=None)

    # 2. Bypass validation by setting the attribute directly to an unsupported type
    config.tz = 123.45  # A float is not handled by the serializer logic

    # 3. Trigger serialization - this will now hit the 'raise' at the end of the serializer
    with pytest.raises(
        ValueError, match="Expected str, ZoneInfo, or timezone, got float"
    ):
        config.model_dump()


def test_calendar_serializer_raise_fallback():
    """Forces the Calendar serializer to hit the final raise."""
    config = CalendarIntervalTriggerConfig(days=1, tz=None)
    config.tz = [1, 2, 3]  # A list

    with pytest.raises(
        ValueError, match="Expected str, ZoneInfo, or timezone, got list"
    ):
        config.model_dump()
