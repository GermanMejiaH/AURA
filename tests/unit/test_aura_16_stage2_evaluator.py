from __future__ import annotations

from datetime import UTC, datetime, timedelta

from aura.cognition.scheduling import (
    EvaluationResult,
    ScheduleEvaluator,
    ScheduleStatus,
    ScheduleType,
    TemporalSchedule,
)


def test_01_one_shot_eligibility_and_completion():
    """Test 01: ONE_SHOT is eligible when next_run_at <= at_timestamp and sets COMPLETED."""
    evaluator = ScheduleEvaluator()
    now = datetime.now(UTC)
    past = (now - timedelta(minutes=5)).isoformat()
    now_iso = now.isoformat()

    sched = TemporalSchedule(
        goal_id="g1",
        schedule_type=ScheduleType.ONE_SHOT,
        next_run_at=past,
    )

    res = evaluator.evaluate_eligibility(sched, at_timestamp=now_iso)
    assert isinstance(res, EvaluationResult)
    assert res.is_eligible is True
    assert res.next_status == ScheduleStatus.COMPLETED
    assert res.calculated_next_run_at is None


def test_02_one_shot_future_not_eligible():
    """Test 02: ONE_SHOT with future next_run_at is not eligible."""
    evaluator = ScheduleEvaluator()
    now = datetime.now(UTC)
    future = (now + timedelta(minutes=10)).isoformat()
    now_iso = now.isoformat()

    sched = TemporalSchedule(
        goal_id="g1",
        schedule_type=ScheduleType.ONE_SHOT,
        next_run_at=future,
    )

    res = evaluator.evaluate_eligibility(sched, at_timestamp=now_iso)
    assert res.is_eligible is False
    assert res.calculated_next_run_at == future


def test_03_one_shot_already_executed_not_eligible():
    """Test 03: ONE_SHOT schedule with iterations_count > 0 is not eligible."""
    evaluator = ScheduleEvaluator()

    sched = TemporalSchedule(
        goal_id="g1",
        schedule_type=ScheduleType.ONE_SHOT,
        iterations_count=1,
    )

    res = evaluator.evaluate_eligibility(sched)
    assert res.is_eligible is False
    assert res.next_status == ScheduleStatus.COMPLETED


def test_04_interval_eligibility_and_next_run():
    """Test 04: INTERVAL schedule computes next_run_at = at_timestamp + interval."""
    evaluator = ScheduleEvaluator()
    now = datetime.now(UTC)
    past = (now - timedelta(minutes=10)).isoformat()
    now_iso = now.isoformat()

    sched = TemporalSchedule(
        goal_id="g1",
        schedule_type=ScheduleType.INTERVAL,
        expression="300",  # 5 minutes
        next_run_at=past,
    )

    res = evaluator.evaluate_eligibility(sched, at_timestamp=now_iso)
    assert res.is_eligible is True

    next_dt = datetime.fromisoformat(res.calculated_next_run_at)
    diff = (next_dt - now).total_seconds()
    assert abs(diff - 300.0) < 2.0


def test_05_interval_overdue_jumps_forward():
    """Test 05: INTERVAL overdue by multiple periods jumps forward relative to at_timestamp."""
    evaluator = ScheduleEvaluator()
    now = datetime.now(UTC)
    overdue_past = (now - timedelta(days=5)).isoformat()
    now_iso = now.isoformat()

    sched = TemporalSchedule(
        goal_id="g1",
        schedule_type=ScheduleType.INTERVAL,
        expression="600",  # 10 minutes
        next_run_at=overdue_past,
    )

    res = evaluator.evaluate_eligibility(sched, at_timestamp=now_iso)
    assert res.is_eligible is True
    assert res.calculated_next_run_at is not None

    next_dt = datetime.fromisoformat(res.calculated_next_run_at)
    # Next run is 10 mins after now_iso, not 5 days ago
    assert next_dt > now


def test_06_cron_parser_and_next_run():
    """Test 06: CRON schedule expression '*/15 * * * *' computes next 15-min boundary."""
    evaluator = ScheduleEvaluator()
    ref_dt = datetime(2026, 8, 15, 10, 3, 0, tzinfo=UTC)
    ref_iso = ref_dt.isoformat()

    sched = TemporalSchedule(
        goal_id="g1",
        schedule_type=ScheduleType.CRON,
        expression="*/15 * * * *",
    )

    res = evaluator.evaluate_eligibility(sched, at_timestamp=ref_iso)
    assert res.is_eligible is True
    assert res.calculated_next_run_at == "2026-08-15T10:15:00+00:00"


def test_07_cron_complex_pattern():
    """Test 07: CRON '30 8 1 * *' computes 8:30 AM on 1st day of next month."""
    evaluator = ScheduleEvaluator()
    ref_dt = datetime(2026, 8, 15, 10, 0, 0, tzinfo=UTC)
    ref_iso = ref_dt.isoformat()

    sched = TemporalSchedule(
        goal_id="g1",
        schedule_type=ScheduleType.CRON,
        expression="30 8 1 * *",
    )

    next_run = evaluator.compute_next_run_at(sched, from_timestamp=ref_iso)
    assert next_run == "2026-09-01T08:30:00+00:00"


def test_08_continuous_eligibility():
    """Test 08: CONTINUOUS schedule is immediately eligible on-demand."""
    evaluator = ScheduleEvaluator()
    now_iso = datetime.now(UTC).isoformat()

    sched = TemporalSchedule(
        goal_id="g1",
        schedule_type=ScheduleType.CONTINUOUS,
    )

    res = evaluator.evaluate_eligibility(sched, at_timestamp=now_iso)
    assert res.is_eligible is True
    assert res.calculated_next_run_at is not None


def test_09_max_iterations_reached():
    """Test 09: Schedule reaching max_iterations is not eligible and transitions to COMPLETED."""
    evaluator = ScheduleEvaluator()

    sched = TemporalSchedule(
        goal_id="g1",
        schedule_type=ScheduleType.INTERVAL,
        expression="60",
        max_iterations=3,
        iterations_count=3,
    )

    res = evaluator.evaluate_eligibility(sched)
    assert res.is_eligible is False
    assert res.next_status == ScheduleStatus.COMPLETED
    assert "Max iterations" in res.reason


def test_10_paused_schedule_not_eligible():
    """Test 10: PAUSED schedule is not eligible."""
    evaluator = ScheduleEvaluator()

    sched = TemporalSchedule(
        goal_id="g1",
        status=ScheduleStatus.PAUSED,
    )

    res = evaluator.evaluate_eligibility(sched)
    assert res.is_eligible is False
    assert "PAUSED" in res.reason


def test_11_completed_and_cancelled_not_eligible():
    """Test 11: COMPLETED or CANCELLED schedules are not eligible."""
    evaluator = ScheduleEvaluator()

    s_comp = TemporalSchedule(goal_id="g1", status=ScheduleStatus.COMPLETED)
    s_canc = TemporalSchedule(goal_id="g2", status=ScheduleStatus.CANCELLED)

    assert evaluator.evaluate_eligibility(s_comp).is_eligible is False
    assert evaluator.evaluate_eligibility(s_canc).is_eligible is False


def test_12_pure_evaluator_no_side_effects():
    """Test 12: ScheduleEvaluator does not mutate TemporalSchedule object fields."""
    evaluator = ScheduleEvaluator()

    sched = TemporalSchedule(
        goal_id="g1",
        schedule_type=ScheduleType.ONE_SHOT,
        iterations_count=0,
        status=ScheduleStatus.ACTIVE,
    )

    original_status = sched.status
    original_count = sched.iterations_count

    evaluator.evaluate_eligibility(sched)

    assert sched.status == original_status
    assert sched.iterations_count == original_count


def test_13_timezone_naive_vs_aware_handling():
    """Test 13: ScheduleEvaluator handles naïve and timezone-aware timestamps seamlessly."""
    evaluator = ScheduleEvaluator()

    sched = TemporalSchedule(
        goal_id="g1",
        schedule_type=ScheduleType.INTERVAL,
        expression="100",
    )

    naive_ts = "2026-08-15T12:00:00"
    aware_ts = "2026-08-15T12:00:00+00:00"

    res_naive = evaluator.evaluate_eligibility(sched, at_timestamp=naive_ts)
    res_aware = evaluator.evaluate_eligibility(sched, at_timestamp=aware_ts)

    assert res_naive.is_eligible is True
    assert res_aware.is_eligible is True
    assert res_naive.calculated_next_run_at == res_aware.calculated_next_run_at


def test_14_cron_invalid_field_count_fallback():
    """Test 14: Expression with != 5 fields falls back safely to +1 hour."""
    evaluator = ScheduleEvaluator()
    ref_dt = datetime(2026, 8, 15, 12, 0, 0, tzinfo=UTC)
    ref_iso = ref_dt.isoformat()

    sched_too_short = TemporalSchedule(
        goal_id="g1", schedule_type=ScheduleType.CRON, expression="* * * *"
    )
    sched_too_long = TemporalSchedule(
        goal_id="g1", schedule_type=ScheduleType.CRON, expression="* * * * * *"
    )

    next_short = evaluator.compute_next_run_at(sched_too_short, from_timestamp=ref_iso)
    next_long = evaluator.compute_next_run_at(sched_too_long, from_timestamp=ref_iso)

    assert next_short == "2026-08-15T13:00:00+00:00"
    assert next_long == "2026-08-15T13:00:00+00:00"


def test_15_cron_invalid_range_and_step_fallback():
    """Test 15: Inverted range, invalid step, and out-of-bounds fallback safely."""
    evaluator = ScheduleEvaluator()
    ref_dt = datetime(2026, 8, 15, 12, 0, 0, tzinfo=UTC)
    ref_iso = ref_dt.isoformat()

    # 15-5 is inverted range, */0 is invalid step, 99 is out-of-bounds minute
    sched = TemporalSchedule(
        goal_id="g1",
        schedule_type=ScheduleType.CRON,
        expression="15-5 */0 99 * *",
    )

    # Parser falls back safely to valid ranges without raising error or looping infinitely
    next_run = evaluator.compute_next_run_at(sched, from_timestamp=ref_iso)
    assert next_run is not None


def test_16_cron_range_with_step():
    """Test 16: Cron range-with-step '1-15/5 * * * *' matches minutes 1, 6, 11."""
    evaluator = ScheduleEvaluator()
    ref_dt = datetime(2026, 8, 15, 12, 0, 0, tzinfo=UTC)
    ref_iso = ref_dt.isoformat()

    sched = TemporalSchedule(
        goal_id="g1",
        schedule_type=ScheduleType.CRON,
        expression="1-15/5 * * * *",
    )

    next_run = evaluator.compute_next_run_at(sched, from_timestamp=ref_iso)
    assert next_run == "2026-08-15T12:01:00+00:00"


def test_17_cron_dow_mapping_sunday():
    """Test 17: Cron dow=7 maps to Sunday (dow=0)."""
    evaluator = ScheduleEvaluator()
    # 2026-08-15 is Saturday. Next Sunday is 2026-08-16.
    ref_dt = datetime(2026, 8, 15, 12, 0, 0, tzinfo=UTC)
    ref_iso = ref_dt.isoformat()

    sched = TemporalSchedule(
        goal_id="g1",
        schedule_type=ScheduleType.CRON,
        expression="0 10 * * 7",  # Sunday at 10:00 AM
    )

    next_run = evaluator.compute_next_run_at(sched, from_timestamp=ref_iso)
    assert next_run == "2026-08-16T10:00:00+00:00"


def test_18_cron_exact_expected_timestamps():
    """Test 18: Exact expected UTC timestamps for standard cron expressions."""
    evaluator = ScheduleEvaluator()
    ref_dt = datetime(2026, 8, 15, 12, 0, 0, tzinfo=UTC)  # Saturday
    ref_iso = ref_dt.isoformat()

    # 0 8 * * 1-5 (Mon-Fri 8:00 AM). Saturday 12:00 -> Next Monday (2026-08-17) at 8:00 AM
    sched_workdays = TemporalSchedule(
        goal_id="g1",
        schedule_type=ScheduleType.CRON,
        expression="0 8 * * 1-5",
    )
    next_workday = evaluator.compute_next_run_at(sched_workdays, from_timestamp=ref_iso)
    assert next_workday == "2026-08-17T08:00:00+00:00"
