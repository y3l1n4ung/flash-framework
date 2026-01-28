from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from flash_scheduler.schemas import CronTriggerConfig
from flash_scheduler.triggers.cron import CronTrigger


@pytest.fixture
def utc():
    return timezone.utc


@pytest.fixture
def jan_1_2026(utc):
    """
    Monday, Jan 1st 2026 00:00:00 UTC.
    This serves as a consistent anchor for deterministic tests.
    """
    return datetime(2026, 1, 1, 0, 0, 0, tzinfo=utc)


def test_every_minute(jan_1_2026):
    """Expr: * * * * * * (Every second)."""
    trigger_config = CronTriggerConfig(second="*")
    trigger = CronTrigger(config=trigger_config)

    # Next fire should be exactly 1 second later
    next_run = trigger.next_fire_time(None, jan_1_2026)
    assert next_run == jan_1_2026 + timedelta(seconds=1)


def test_every_15_minutes(jan_1_2026):
    """Expr: 0 */15 * * * *."""
    trigger_config = CronTriggerConfig(second="0", minute="*/15")
    trigger = CronTrigger(config=trigger_config)

    # 00:00 -> 00:15
    next_run = trigger.next_fire_time(None, jan_1_2026)
    assert next_run == jan_1_2026.replace(minute=15)

    # 00:15 -> 00:30
    assert next_run
    next_run_2 = trigger.next_fire_time(None, next_run)
    assert next_run_2 == jan_1_2026.replace(minute=30)


def test_specific_time(jan_1_2026):
    """Expr: 30 0 9 * * * (9:00:30 AM daily)."""
    trigger_config = CronTriggerConfig(hour="9", minute="0", second="30")
    trigger = CronTrigger(config=trigger_config)

    next_run = trigger.next_fire_time(None, jan_1_2026)
    assert next_run == jan_1_2026.replace(hour=9, minute=0, second=30)


def test_day_of_week_execution(jan_1_2026, utc):
    """Expr: * * * * * MON (Only run on Mondays)."""
    trigger_conf = CronTriggerConfig(
        day_of_week="MON",
        hour="12",
        minute="0",
        second="0",
    )
    trigger = CronTrigger(config=trigger_conf)

    # 1. Start on Jan 1 (Thursday)
    # Since today is Thu, it must wait for the first Monday -> Jan 5th
    run_first_mon = trigger.next_fire_time(None, jan_1_2026)
    assert run_first_mon
    assert run_first_mon.day == 5  # Jan 5th is the first Monday of 2026
    assert run_first_mon.month == 1
    assert run_first_mon.hour == 12

    # 2. Skip past that Monday to Tuesday, Jan 6th
    tues_jan_6 = datetime(2026, 1, 6, 12, 0, tzinfo=utc)

    # Next run should be the following Monday -> Jan 12th
    run_next = trigger.next_fire_time(None, tues_jan_6)
    assert run_next
    assert run_next.day == 12
    assert run_next.month == 1


def test_list_and_range_parsing(jan_1_2026):
    """Expr: 0 0 9-11,15 * * * (Hours: 9, 10, 11, 15)."""
    trigger_conf = CronTriggerConfig(hour="9-11,15", minute="0")
    trigger = CronTrigger(config=trigger_conf)

    # 00:00 -> 09:00
    run_1 = trigger.next_fire_time(None, jan_1_2026)
    assert run_1

    assert run_1.hour == 9

    # 09:00 -> 10:00
    run_2 = trigger.next_fire_time(None, run_1)
    assert run_2
    assert run_2.hour == 10

    # 11:00 -> 15:00 (Skip 12, 13, 14)
    run_3 = jan_1_2026.replace(hour=11)
    run_4 = trigger.next_fire_time(None, run_3)
    assert run_4
    assert run_4.hour == 15


def test_month_rollover(utc):
    """Expr: * * * 1 JAN * (Only Jan 1st)."""
    trigger = CronTrigger(CronTriggerConfig(month="JAN", day="1", hour="0", minute="0"))

    # Current: Jan 2nd 2024
    now = datetime(2024, 1, 2, tzinfo=utc)

    # Should skip the rest of 2024 and find Jan 1st 2025
    next_run = trigger.next_fire_time(None, now)
    assert next_run
    assert next_run.year == 2025
    assert next_run.month == 1
    assert next_run.day == 1


def test_leap_year_handling(utc):
    """Expr: * * * 29 FEB * (Only Feb 29th)."""
    trigger = CronTrigger(
        CronTriggerConfig(month="FEB", day="29", hour="0", minute="0"),
    )

    # Start 2023 (Non-leap year)
    now = datetime(2023, 1, 1, tzinfo=utc)

    # Should skip 2023 completely and find Feb 29, 2024
    next_run = trigger.next_fire_time(None, now)

    assert next_run
    assert next_run.year == 2024
    assert next_run.month == 2
    assert next_run.day == 29


def test_from_string_standard_5_fields():
    """Test standard Linux cron format (minute based)."""
    # "30 9 * * *" -> 09:30:00 daily
    trigger = CronTrigger.from_string("30 9 * * *")

    assert trigger.second == "0"  # Default for 5-field strings
    assert trigger.minute == "30"
    assert trigger.hour == "9"
    # Ensure parsing happened correctly
    assert trigger._minute.matches(30)


def test_from_string_extended_6_fields():
    """Test extended format including seconds."""
    # "15 30 9 * * *" -> 09:30:15 daily
    trigger = CronTrigger.from_string("15 30 9 * * *")

    assert trigger.second == "15"
    assert trigger.minute == "30"
    assert trigger.hour == "9"


def test_from_string_invalid_format():
    """Ensure malformed strings raise error."""
    with pytest.raises(ValueError, match="Expected 5 or 6 fields"):
        CronTrigger.from_string("Too few fields")


def test_invalid_range_raises_error():
    """Minute 61 should fail validation."""
    with pytest.raises(ValueError, match="out of range"):
        CronTrigger(CronTriggerConfig(minute="61"))


def test_invalid_alias_usage():
    """Month 13 should fail validation."""
    with pytest.raises(ValueError):
        CronTrigger(CronTriggerConfig(month="13"))


@patch("random.uniform")
def test_cron_jitter(mock_random, jan_1_2026):
    """Ensure jitter is added to the final calculated cron time."""
    mock_random.return_value = 10.0
    trigger = CronTrigger(
        CronTriggerConfig(second="0", minute="0", hour="*", jitter=30),
    )

    # Current: 00:59:00
    now = jan_1_2026.replace(hour=0, minute=59)

    # Next cron hit: 01:00:00. Plus jitter: 01:00:10.
    next_run = trigger.next_fire_time(None, now)

    assert next_run
    assert next_run.hour == 1
    assert next_run.minute == 0
    assert next_run.second == 10


def test_validation_out_of_bounds_hit():
    """
    Forces the validator loop to execute and raise ValueError.
    """
    # Minute range is 0-59. '60' is parsed successfully as an int,
    # but fails the range check inside the validation loop.
    with pytest.raises(ValueError, match="Value 60 out of range"):
        CronTrigger(CronTriggerConfig(minute="60"))

    # Hour range is 0-23. '24' should fail.
    with pytest.raises(ValueError, match="Value 24 out of range"):
        CronTrigger(CronTriggerConfig(hour="24"))


def test_from_string_extended_6_parts_hit():
    """
    Explicitly calls from_string with 6 parts to hit the `elif num_parts == 6:` block.
    Covers line 256.
    """
    # "10 30 9 * * *" -> 9:30:10 AM
    trigger = CronTrigger.from_string("10 30 9 * * *")

    assert trigger.second == "10"
    assert trigger.minute == "30"
    assert trigger.hour == "9"
    # Verify internal field compilation
    assert trigger._second.matches(10)


def test_impossible_schedule_returns_none(utc):
    """
    Creates a schedule that is mathematically impossible (e.g., Feb 30th).
    The trigger will loop 1000 times (max_iterations), fail to find a match,
    and fall through to the final return.

    """
    # February never has 30 days.
    # Logic:
    # 1. Matches Month (Feb) -> OK
    # 2. Checks Day (30) -> Invalid for Feb
    # 3. Calls _advance_day -> Sees 30 is > 28/29 -> Calls _advance_month
    # 4. Jumps to next year's Feb.
    # 5. Repeats 1000 times until loop exhausts.
    trigger_config = CronTriggerConfig(month="FEB", day="30")
    trigger = CronTrigger(config=trigger_config)

    now = datetime(2024, 1, 1, tzinfo=utc)

    # Should return None because it gives up after 1000 failed attempts
    result = trigger.next_fire_time(None, now)

    assert result is None


def test_parse_range_step_syntax():
    """
    Tests parsing logic for range-based steps.
    Input: "0-10/5"
    Logic: Parse '0-10' as the range, and step by '5'.
    Expected: {0, 5, 10}
    """
    trigger_config = CronTriggerConfig(second="0-10/5")
    trigger = CronTrigger(config=trigger_config)

    assert trigger._second.matches(0)
    assert trigger._second.matches(5)
    assert trigger._second.matches(10)

    # Validation: Should NOT match values outside the step or range
    assert not trigger._second.matches(15)  # Out of range (>10)
    assert not trigger._second.matches(3)  # Not a multiple of 5


def test_parse_implicit_max_step_syntax():
    """
    Tests parsing logic for steps with only a start value.
    Input: "30/10"
    Logic: Parse '30' as start, implicit max (59) as end, step by '10'.
    Expected: {30, 40, 50}
    """
    trigger_config = CronTriggerConfig(second="30/10")
    trigger = CronTrigger(config=trigger_config)

    assert trigger._second.matches(30)
    assert trigger._second.matches(40)
    assert trigger._second.matches(50)

    # Validation
    assert not trigger._second.matches(20)  # Before start
    assert not trigger._second.matches(35)  # Not in step increment


def test_hour_rollover_logic(utc):
    """
    Tests the branching logic in _advance_hour.

    Scenario 1 (Advancement): Next valid hour is later today.
    Scenario 2 (Rollover): No valid hours left today; must roll over to tomorrow.
    """
    # Configuration: Run only at 09:00 and 12:00
    trigger_config = CronTriggerConfig(hour="9,12", minute="0")
    trigger = CronTrigger(config=trigger_config)

    # --- Case 1: Simple Advancement ---
    # Start at 10:00 -> Next valid slot is 12:00 (Same Day)
    start_same_day = datetime(2024, 1, 1, 10, 0, tzinfo=utc)
    next_run = trigger.next_fire_time(None, start_same_day)

    assert next_run
    assert next_run.day == 1
    assert next_run.hour == 12

    # --- Case 2: Rollover to Next Day ---
    # Start at 13:00 -> Missed both 9 and 12. Must wait for 9:00 Tomorrow.
    start_next_day = datetime(2024, 1, 1, 13, 0, tzinfo=utc)
    next_run_rollover = trigger.next_fire_time(None, start_next_day)
    assert next_run_rollover
    assert next_run_rollover.day == 2  # Rolled over to Jan 2nd
    assert next_run_rollover.hour == 9
