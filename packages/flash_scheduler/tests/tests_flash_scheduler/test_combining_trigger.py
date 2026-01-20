from flash_scheduler.schemas import CronTriggerConfig, IntervalTriggerConfig
from flash_scheduler.triggers.date import DateTrigger
import pytest
from datetime import datetime, timezone, timedelta
from flash_scheduler.triggers.combining import AndTrigger, OrTrigger
from flash_scheduler.triggers.cron import CronTrigger
from flash_scheduler.triggers.interval import IntervalTrigger


@pytest.fixture
def utc():
    return timezone.utc


@pytest.fixture
def jan_1_2026(utc):
    """
    Thursday, Jan 1st 2026 00:00:00 UTC.
    Used as the anchor for all deterministic tests.
    """
    return datetime(2026, 1, 1, 0, 0, 0, tzinfo=utc)


def test_and_trigger_basic_overlap(jan_1_2026):
    """
    Scenario: Run every Monday (Cron) AND every day at 10:00 AM (Cron).
    Context: Jan 1, 2026 is a Thursday.
    Logic: The scheduler must wait for the first Monday (Jan 5).
    """
    t1_config = CronTriggerConfig(day_of_week="MON")  # Mondays
    t1 = CronTrigger(config=t1_config)  # Mondays
    t2_config = CronTriggerConfig(hour="10", minute="0")  # 10:00 AM
    t2 = CronTrigger(config=t2_config)  # 10:00 AM

    and_trigger = AndTrigger([t1, t2])

    # 1. Run from Jan 1 (Thu)
    next_run = and_trigger.next_fire_time(None, jan_1_2026)

    # Expect: Jan 5th (First Monday) at 10:00 AM
    assert next_run
    assert next_run.year == 2026
    assert next_run.month == 1
    assert next_run.day == 5
    assert next_run.hour == 10

    # 2. Run from Jan 5th 11:00 AM
    # Should skip Tuesday-Sunday and find Jan 12th (Next Monday)
    next_run_2 = and_trigger.next_fire_time(None, next_run + timedelta(hours=1))
    assert next_run_2
    assert next_run_2.day == 12
    assert next_run_2.hour == 10


def test_and_trigger_impossible(jan_1_2026):
    """
    Scenario: 'Every Monday' AND 'Every Tuesday'.
    Logic: Impossible to be both days at once. Should return None.
    """
    t1_config = CronTriggerConfig(day_of_week="MON")
    t1 = CronTrigger(config=t1_config)
    t2_config = CronTriggerConfig(day_of_week="TUE")
    t2 = CronTrigger(config=t2_config)

    and_trigger = AndTrigger([t1, t2])

    result = and_trigger.next_fire_time(None, jan_1_2026)
    assert result is None


def test_and_trigger_validation():
    """Requires at least 2 triggers."""
    with pytest.raises(ValueError, match="requires at least 2 triggers"):
        AndTrigger([CronTrigger(CronTriggerConfig(minute="*"))])


def test_or_trigger_earliest_wins(jan_1_2026):
    """
    Scenario: 'Every 10 mins' OR 'Every 1 hour'.
    Logic: Should return 10 mins because it occurs sooner than 1 hour.
    """
    t1_config = IntervalTriggerConfig(minutes=10)
    t1 = IntervalTrigger(config=t1_config)
    t2_config = IntervalTriggerConfig(hours=1)
    t2 = IntervalTrigger(config=t2_config)

    or_trigger = OrTrigger([t1, t2])

    next_run = or_trigger.next_fire_time(None, jan_1_2026)

    # 10 mins is sooner than 1 hour
    assert next_run == jan_1_2026 + timedelta(minutes=10)


def test_or_trigger_interleaved(jan_1_2026):
    """
    Scenario: 'At min 5' OR 'At min 10'.
    Logic: Should fire at 00:05, then 00:10.
    """
    t1_config = CronTriggerConfig(minute="5")
    t1 = CronTrigger(config=t1_config)
    t2_config = CronTriggerConfig(minute="10")
    t2 = CronTrigger(config=t2_config)

    or_trigger = OrTrigger([t1, t2])

    # 1. First run -> 00:05
    run_1 = or_trigger.next_fire_time(None, jan_1_2026)
    assert run_1
    assert run_1.minute == 5

    # 2. Second run -> 00:10
    run_2 = or_trigger.next_fire_time(None, run_1)
    assert run_2
    assert run_2.minute == 10


def test_or_trigger_validation():
    """Requires at least 2 triggers."""
    with pytest.raises(ValueError, match="requires at least 2 triggers"):
        OrTrigger([])


def test_and_trigger_finishes_when_one_child_finishes(utc):
    """
    Scenario: One trigger is still valid (future), but the other is finished (past).
    Result: The AndTrigger should stop immediately.
    """
    # Valid trigger (Future)
    future_date = datetime(3000, 1, 1, tzinfo=utc)
    t1 = DateTrigger(run_at=future_date)

    # Finished trigger (Past)
    past_date = datetime(2000, 1, 1, tzinfo=utc)
    t2 = DateTrigger(run_at=past_date)

    and_trigger = AndTrigger([t1, t2])

    # "Now" is 2026
    now = datetime(2026, 1, 1, tzinfo=utc)

    # Since t2 returns None, AndTrigger must return None
    assert and_trigger.next_fire_time(None, now) is None


def test_or_trigger_finishes_when_all_children_finish(utc):
    """
    Scenario: All triggers are finished (past).
    Result: The OrTrigger should stop.
    """
    past_date = datetime(2000, 1, 1, tzinfo=utc)

    # Both triggers are done
    t1 = DateTrigger(run_at=past_date)
    t2 = DateTrigger(run_at=past_date)

    or_trigger = OrTrigger([t1, t2])

    # "Now" is 2026
    now = datetime(2026, 1, 1, tzinfo=utc)

    # No potential times collected -> returns None
    assert or_trigger.next_fire_time(None, now) is None
