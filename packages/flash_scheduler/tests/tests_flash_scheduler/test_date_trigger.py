from datetime import datetime, timedelta, timezone

import pytest
from flash_scheduler.triggers.date import DateTrigger

# --- Fixtures ---


@pytest.fixture
def utc():
    return timezone.utc


@pytest.fixture
def future_date(utc):
    """A deterministic future date: Jan 1st, 3000."""
    return datetime(3000, 1, 1, 12, 0, 0, tzinfo=utc)


# --- Test Cases ---


def test_validation_error_naive_datetime():
    """Ensure validation fails if a timezone-naive datetime is provided."""
    # Create a naive datetime by removing timezone from an aware datetime
    aware_dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
    naive_dt = aware_dt.replace(tzinfo=None)  # No timezone info

    with pytest.raises(ValueError, match="run_at must be timezone-aware"):
        DateTrigger(run_at=naive_dt)


def test_next_fire_time_future(future_date):
    """
    Test standard behavior: Scheduled time is in the future.
    Logic: Should return the exact run_at.
    """
    trigger = DateTrigger(run_at=future_date)

    # 'now' is well before the future date
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)

    next_run = trigger.next_fire_time(None, now)
    assert next_run == future_date


def test_next_fire_time_past(future_date):
    """
    Test behavior when the scheduled time has already passed.
    Logic: If run_at <= now, we missed it. Return None (don't run stale jobs).
    """
    trigger = DateTrigger(run_at=future_date)

    # 'now' is AFTER the scheduled date
    now_past = future_date + timedelta(seconds=1)

    next_run = trigger.next_fire_time(None, now_past)
    assert next_run is None


def test_next_fire_time_already_ran(future_date):
    """
    Test behavior after the job has executed once.
    Logic: DateTrigger is one-off. If 'previous_fire_time' exists, return None.
    """
    trigger = DateTrigger(run_at=future_date)

    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    previous_run = future_date  # Simulating it ran successfully

    next_run = trigger.next_fire_time(previous_run, now)
    assert next_run is None


def test_repr(future_date):
    """
    Verify base class repr output works correctly.
    Should output: DateTrigger(run_at=datetime(...))
    """
    trigger = DateTrigger(run_at=future_date)
    assert "DateTrigger" in repr(trigger)
    assert "3000" in repr(trigger)  # Checks that the year is present in the string
