from flash_scheduler.schemas import IntervalTriggerConfig
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from flash_scheduler.triggers.interval import IntervalTrigger


@pytest.fixture
def utc():
    return timezone.utc


@pytest.fixture
def now_utc(utc):
    """Fixed 'current time' for deterministic testing: Jan 1st, 2026 at 12:00:00 UTC."""
    return datetime(2026, 1, 1, 12, 0, 0, tzinfo=utc)


# --- Test Cases ---


def test_validation_error():
    """Ensure the trigger raises an error if the interval is 0 or negative."""
    with pytest.raises(ValueError, match="interval must be positive"):
        IntervalTrigger(IntervalTriggerConfig(seconds=0))


def test_first_run_calculation(now_utc):
    """
    Test the very first execution of a job.
    Logic: If never run before, next fire time should be NOW + INTERVAL.
    """
    trigger = IntervalTrigger(IntervalTriggerConfig(minutes=10))

    # Passing None as 'previous_fire_time' simulates the first run
    next_run = trigger.next_fire_time(None, now_utc)

    # 12:00 + 10m = 12:10
    assert next_run == now_utc + timedelta(minutes=10)


def test_first_run_with_start_time(now_utc):
    """
    Test first execution when a specific 'start_time' is enforced.
    Logic: If start_time is in the future, wait until then.
    """
    # Set start time to 13:00 (1 hour in the future)
    start = now_utc + timedelta(hours=1)
    trigger = IntervalTrigger(IntervalTriggerConfig(minutes=10, start_time=start))

    next_run = trigger.next_fire_time(None, now_utc)

    # Should return 13:00 exactly, ignoring the interval for now
    assert next_run == start


def test_subsequent_run_normal(now_utc):
    """
    Test standard recurring execution.
    Logic: Next run = Previous run + Interval.
    """
    trigger = IntervalTrigger(IntervalTriggerConfig(minutes=10))
    prev_run = now_utc  # 12:00

    # Simulating the scheduler checking at 12:05
    check_time = now_utc + timedelta(minutes=5)

    next_run = trigger.next_fire_time(prev_run, check_time)

    # Should be 12:10. The check_time (12:05) shouldn't affect the schedule.
    assert next_run == prev_run + timedelta(minutes=10)


def test_catchup_logic(now_utc):
    """
    Test the 'Catch-up' mechanism for missed jobs.
    Scenario: System went down at 12:00 and woke up at 12:35.
    We missed the 12:10, 12:20, and 12:30 runs.
    Logic: Skip the missed runs and schedule for the next valid slot (12:40).
    """
    trigger = IntervalTrigger(IntervalTriggerConfig(minutes=10))
    prev_run = now_utc  # 12:00

    # Current time is 12:35
    check_time = now_utc + timedelta(minutes=35)

    next_run = trigger.next_fire_time(prev_run, check_time)

    # Expected: 12:00 + 10 + 10 + 10 + 10 = 12:40
    expected = now_utc + timedelta(minutes=40)
    assert next_run == expected


def test_end_time_constraint(now_utc):
    """
    Test that the trigger stops firing after 'end_time'.
    Scenario: Schedule ends at 12:05. Next run calculated is 12:10.
    Logic: Since 12:10 > 12:05, return None (stop scheduling).
    """
    end = now_utc + timedelta(minutes=5)  # Ends at 12:05
    trigger = IntervalTrigger(IntervalTriggerConfig(minutes=10, end_time=end))

    next_run = trigger.next_fire_time(None, now_utc)

    # Should stop
    assert next_run is None


def test_now_past_end_time(now_utc):
    """
    Test immediate exit if the trigger is obsolete.
    Scenario: 'Now' is already past the 'end_time'.
    Logic: Return None immediately.
    """
    end = now_utc - timedelta(minutes=1)  # Ended 1 min ago
    trigger = IntervalTrigger(IntervalTriggerConfig(minutes=10, end_time=end))

    assert trigger.next_fire_time(None, now_utc) is None


@patch("random.uniform")
def test_jitter(mock_random, now_utc):
    """
    Test the 'Jitter' (random delay) functionality.
    We use @patch to force the random number to be deterministic (5.0).
    Logic: Final Time = Scheduled Time + Jitter.
    """
    # Force random.uniform to return exactly 5.0 seconds
    mock_random.return_value = 5.0

    trigger = IntervalTrigger(IntervalTriggerConfig(minutes=10, jitter=10))

    next_run = trigger.next_fire_time(None, now_utc)

    # 12:00 + 10min = 12:10:00 -> add 5s jitter -> 12:10:05
    expected = now_utc + timedelta(minutes=10, seconds=5)
    assert next_run == expected


def test_repr():
    """
    Verify the string representation (used for debugging logs).
    We check if the correct class name and timedelta are present.
    """
    t = IntervalTrigger(IntervalTriggerConfig(weeks=1))

    # 'weeks=1' becomes 'days=7' in python timedelta
    assert "IntervalTrigger" in repr(t)
    assert "days=7" in repr(t)


def test_init_with_direct_interval_object():
    """
    Test initialization using a direct timedelta object.
    """
    # Create a specific timedelta (e.g., 2 hours)
    direct_interval = timedelta(hours=2)

    # Pass it to the trigger, also passing 'minutes=30' to ensure it gets ignored
    trigger = IntervalTrigger(
        IntervalTriggerConfig(minutes=30, interval=direct_interval)
    )

    # The trigger should use the direct object (2 hours), NOT the minutes (30 mins)
    assert trigger.interval == direct_interval
    assert trigger.interval.total_seconds() == 7200  # 2 hours * 3600


def test_interval_positive():
    with pytest.raises(ValueError):
        IntervalTrigger(IntervalTriggerConfig(interval=timedelta(0)))
