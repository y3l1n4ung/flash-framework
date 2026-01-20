from flash_scheduler.schemas import CalendarIntervalTriggerConfig
from pydantic import ValidationError
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

# Update this import path to match your actual package structure
from flash_scheduler.triggers import CalendarIntervalTrigger, Trigger


# --- Fixtures ---
@pytest.fixture
def utc():
    return timezone.utc


class SimpleTrigger(Trigger):
    """A basic implementation for testing."""

    def __init__(self, interval: int):
        self.interval = interval

    def next_fire_time(self, prev_fire_time, now):
        return None


class OtherTrigger(Trigger):
    """A different implementation to test type mismatch."""

    def next_fire_time(self, prev_fire_time, now):
        return None


def test_equality():
    """Equality depends on same class and same attributes."""
    t1 = SimpleTrigger(interval=10)
    t2 = SimpleTrigger(interval=10)
    t3 = SimpleTrigger(interval=20)

    assert t1 == t2  # Same attributes -> Equal
    assert t1 != t3  # Different attributes -> Not Equal
    assert t1 != "string"  # Different type -> Not Equal
    assert t1 != OtherTrigger()


def test_hashing():
    """Equal objects must have the same hash."""
    t1 = SimpleTrigger(interval=10)
    t2 = SimpleTrigger(interval=10)

    assert hash(t1) == hash(t2)
    assert len({t1, t2}) == 1  # Set removes duplicates


def test_repr():
    """String representation should include class name and attrs."""
    t1 = SimpleTrigger(interval=99)
    assert repr(t1) == "SimpleTrigger(interval=99)"


@pytest.fixture
def jan_1_2024(utc):
    """Start of a leap year."""
    return datetime(2024, 1, 1, 0, 0, 0, tzinfo=utc)


def test_validation_error_on_empty_args():
    """Should raise error if no interval is provided."""
    with pytest.raises(
        ValidationError,
        match="At least one of years, months, weeks, or days must be specified",
    ):
        config = CalendarIntervalTriggerConfig(hour=9)
        CalendarIntervalTrigger(config=config)


def test_simple_month_interval(jan_1_2024):
    """Basic Case: 1 month interval from Jan 1st should be Feb 1st."""
    config = CalendarIntervalTriggerConfig(months=1)
    trigger = CalendarIntervalTrigger(config=config)

    # 1. First run
    next_run = trigger.next_fire_time(None, jan_1_2024)
    # Since calculated start (Jan 1 00:00) <= now (Jan 1 00:00), it advances to Feb 1
    assert next_run == datetime(2024, 2, 1, 0, 0, 0, tzinfo=timezone.utc)

    # 2. Second run
    subsequent_run = trigger.next_fire_time(next_run, jan_1_2024)
    assert subsequent_run == datetime(2024, 3, 1, 0, 0, 0, tzinfo=timezone.utc)


def test_month_end_clipping_logic(utc):
    """Edge Case: Jan 31 + 1 month should be Feb 29 (Leap Year) or Feb 28."""
    config = CalendarIntervalTriggerConfig(months=1)

    trigger = CalendarIntervalTrigger(config)

    # Case A: Leap Year (2024)
    jan_31 = datetime(2024, 1, 31, 12, 0, tzinfo=utc)
    next_run = trigger.next_fire_time(jan_31, jan_31)
    assert next_run
    assert next_run.day == 29
    assert next_run.month == 2

    # Case B: Non-Leap Year (2025)
    jan_31_2025 = datetime(2025, 1, 31, 12, 0, tzinfo=utc)
    next_run_2025 = trigger.next_fire_time(jan_31_2025, jan_31_2025)
    assert next_run_2025
    assert next_run_2025.day == 28
    assert next_run_2025.month == 2


def test_specific_time_execution(jan_1_2024):
    """Should respect hour, minute, second arguments."""
    config = CalendarIntervalTriggerConfig(days=1, hour=14, minute=30)
    trigger = CalendarIntervalTrigger(config=config)
    # "Now" is 10:00 AM. Next run should be today at 14:30.
    now = jan_1_2024.replace(hour=10)
    next_run = trigger.next_fire_time(None, now)

    assert next_run == jan_1_2024.replace(hour=14, minute=30)


def test_start_time_constraint(utc):
    """Should not fire before start_time."""
    start_date = datetime(2025, 1, 1, tzinfo=utc)
    config = CalendarIntervalTriggerConfig(days=1, start_time=start_date)
    trigger = CalendarIntervalTrigger(config=config)

    # Current time is 2024
    now = datetime(2024, 1, 1, tzinfo=utc)
    next_run = trigger.next_fire_time(None, now)

    assert next_run == start_date


def test_end_time_constraint(utc):
    """Should return None if next fire time is past end_time."""
    end_date = datetime(2024, 1, 5, tzinfo=utc)
    config = CalendarIntervalTriggerConfig(days=1, end_time=end_date)
    trigger = CalendarIntervalTrigger(config=config)

    now = datetime(2024, 1, 4, tzinfo=utc)
    prev_run = datetime(2024, 1, 4, tzinfo=utc)

    # Next run Jan 5th (OK)
    next_run = trigger.next_fire_time(prev_run, now)
    assert next_run is not None

    # Next run Jan 6th (Blocked)
    final_run = trigger.next_fire_time(next_run, now)
    assert final_run is None


def test_timezone_conversion(utc):
    """Logic should handle TZ conversion correctly."""
    # Define UTC+5
    tz_plus_5 = timezone(timedelta(hours=5))

    # Trigger set for 10:00 AM local time (UTC+5)
    config = CalendarIntervalTriggerConfig(days=1, hour=10, tz=tz_plus_5)
    trigger = CalendarIntervalTrigger(config=config)

    now = datetime(2024, 1, 1, 0, 0, tzinfo=utc)
    next_run = trigger.next_fire_time(None, now)

    # 10:00 AM (UTC+5) == 05:00 AM (UTC)
    assert next_run
    assert next_run.hour == 5
    assert next_run.tzinfo == utc


def test_catchup_logic(jan_1_2024):
    """Should skip missed intervals if system was down."""
    config = CalendarIntervalTriggerConfig(months=1)
    trigger = CalendarIntervalTrigger(config=config)
    last_run = jan_1_2024

    # System wakes up in April
    now = datetime(2024, 4, 15, tzinfo=timezone.utc)

    # Should calculate: Feb -> March -> April -> May
    next_run = trigger.next_fire_time(last_run, now)

    assert next_run == datetime(2024, 5, 1, tzinfo=timezone.utc)


@patch("random.uniform")
def test_jitter_application(mock_random, jan_1_2024):
    """Should add random seconds to result using mock."""
    # Force random to return 30.5 seconds
    mock_random.return_value = 30.5

    config = CalendarIntervalTriggerConfig(days=1, jitter=60)
    trigger = CalendarIntervalTrigger(config=config)

    next_run = trigger.next_fire_time(None, jan_1_2024)

    # Expected: Jan 1 (Start) -> Jan 2 (Interval) + 30.5s Jitter
    expected = datetime(2024, 1, 2, 0, 0, 30, 500000, tzinfo=timezone.utc)

    assert next_run == expected
    mock_random.assert_called_with(0, 60)


def test_repr_method():
    """Ensure string representation works."""
    config = CalendarIntervalTriggerConfig(years=1, months=2, jitter=60)
    trigger = CalendarIntervalTrigger(config=config)

    repr_str = repr(trigger)

    # Verify key parts are in the string
    assert "CalendarIntervalTrigger" in repr_str
    assert "years=1" in repr_str
    assert "months=2" in repr_str
    assert "jitter=60" in repr_str


def test_now_is_past_end_time(utc):
    """Early exit when current time is already past end_time."""
    end_date = datetime(2023, 1, 1, tzinfo=utc)
    config = CalendarIntervalTriggerConfig(days=1, end_time=end_date)
    trigger = CalendarIntervalTrigger(config=config)

    # "Now" is in 2024 (way past the end date)
    now = datetime(2024, 1, 1, tzinfo=utc)

    # Should return None immediately without doing any calculation
    next_run = trigger.next_fire_time(None, now)
    assert next_run is None


def test_init_raises_error_if_empty():
    """Ensure initialization fails if no interval is given."""
    with pytest.raises(
        ValueError,
        match="At least one of years, months, weeks, or days must be specified",
    ):
        # No args provided
        config = CalendarIntervalTriggerConfig()
        CalendarIntervalTrigger(config=config)


def test_next_fire_time_first_run(jan_1_2024):
    """Lines 79-90: Test the first execution calculation."""
    # Run every month
    config = CalendarIntervalTriggerConfig(months=1, hour=9)
    trigger = CalendarIntervalTrigger(config=config)

    # 'now' is Jan 1st 00:00. Trigger wants 9:00.
    # Logic: 9:00 is in the future relative to 'now', so it should just return Jan 1st 09:00.
    next_run = trigger.next_fire_time(None, jan_1_2024)

    assert next_run == jan_1_2024.replace(hour=9)


def test_next_fire_time_subsequent_run(jan_1_2024):
    """Lines 91-98: Test calculating the next interval from a previous one."""
    config = CalendarIntervalTriggerConfig(months=1)
    trigger = CalendarIntervalTrigger(config=config)

    # Previous run was Jan 1st
    prev_run = jan_1_2024

    # 'now' is Jan 15th
    now = jan_1_2024 + timedelta(days=15)

    # Should calculate Feb 1st
    next_run = trigger.next_fire_time(prev_run, now)

    assert next_run == datetime(2024, 2, 1, tzinfo=timezone.utc)
