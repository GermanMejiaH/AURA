from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .models import ScheduleStatus, ScheduleType, TemporalSchedule


def _parse_utc_iso(ts: str | None) -> datetime:
    """Parses an ISO timestamp string to a UTC datetime object."""
    if not ts or not ts.strip():
        return datetime.now(UTC)
    try:
        dt = datetime.fromisoformat(ts.strip())
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:
        return datetime.now(UTC)


def _format_utc_iso(dt: datetime) -> str:
    """Formats a UTC datetime object to an ISO 8601 string."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)
    return dt.isoformat()


def parse_cron_field(field_str: str, min_val: int, max_val: int) -> set[int]:
    """Parses a single 5-part cron field string into a set of allowed integer values.

    Contract: Standard 5-field subset (minute: 0-59, hour: 0-23, dom: 1-31, month: 1-12, dow: 0-6).
    Maps dow=7 to 0 (Sunday). Handles *, */N, A-B, A-B/N, and comma lists.
    Safely falls back to full range for invalid/out-of-bounds inputs or inverted ranges.
    """
    field_str = field_str.strip()
    if not field_str:
        return set(range(min_val, max_val + 1))

    allowed: set[int] = set()

    for part in field_str.split(","):
        part = part.strip()
        if not part:
            continue

        # Handle step suffix (e.g., */15 or 1-15/3)
        step = 1
        sub_part = part
        if "/" in part:
            sub_parts = part.split("/", 1)
            sub_part = sub_parts[0].strip()
            step_str = sub_parts[1].strip()
            if step_str.isdigit() and int(step_str) > 0:
                step = int(step_str)
            else:
                step = 1

        if sub_part == "*":
            allowed.update(
                val for val in range(min_val, max_val + 1) if (val - min_val) % step == 0
            )
        elif "-" in sub_part:
            match = re.match(r"^(\d+)-(\d+)$", sub_part)
            if match:
                start, end = int(match.group(1)), int(match.group(2))
                if start <= end:
                    start = max(min_val, min(start, max_val))
                    end = max(min_val, min(end, max_val))
                    allowed.update(
                        val for val in range(start, end + 1) if (val - start) % step == 0
                    )
        elif sub_part.isdigit():
            val = int(sub_part)
            if val == 7 and max_val == 6:  # Map 7 to 0 (Sunday)
                val = 0
            if min_val <= val <= max_val:
                allowed.add(val)

    return allowed or set(range(min_val, max_val + 1))


def compute_next_cron_time(expression: str, from_dt: datetime) -> datetime:
    """Computes the next future matching UTC datetime for a 5-part cron expression."""
    fields = expression.strip().split()
    if len(fields) != 5:
        # Fallback for invalid cron syntax: default to 1 hour ahead
        return from_dt + timedelta(hours=1)

    min_set = parse_cron_field(fields[0], 0, 59)
    hour_set = parse_cron_field(fields[1], 0, 23)
    dom_set = parse_cron_field(fields[2], 1, 31)
    month_set = parse_cron_field(fields[3], 1, 12)
    dow_set = parse_cron_field(fields[4], 0, 6)

    curr = (from_dt + timedelta(minutes=1)).replace(second=0, microsecond=0)
    # Search up to 525600 minutes (1 year)
    limit = curr + timedelta(days=366)

    while curr <= limit:
        # Match day of week (Python isoweekday: Mon=1..Sun=7, map Sun to 0)
        curr_dow = 0 if curr.isoweekday() == 7 else curr.isoweekday()

        if (
            curr.month in month_set
            and curr.day in dom_set
            and curr_dow in dow_set
            and curr.hour in hour_set
            and curr.minute in min_set
        ):
            return curr

        curr += timedelta(minutes=1)

    return from_dt + timedelta(hours=1)


@dataclass(frozen=True)
class EvaluationResult:
    """Immutable result produced by ScheduleEvaluator."""

    is_eligible: bool
    schedule_id: str
    goal_id: str
    current_status: ScheduleStatus
    next_status: ScheduleStatus
    calculated_next_run_at: str | None
    reason: str


class ScheduleEvaluator:
    """Pure, deterministic evaluation engine for TemporalSchedule eligibility and next_run_at."""

    def evaluate_eligibility(
        self,
        schedule: TemporalSchedule,
        at_timestamp: str | None = None,
    ) -> EvaluationResult:
        """Evaluates whether a schedule is eligible for execution at at_timestamp cleanly."""
        ref_dt = _parse_utc_iso(at_timestamp)
        ref_iso = _format_utc_iso(ref_dt)

        # 1. Non-active status check
        if schedule.status != ScheduleStatus.ACTIVE:
            return EvaluationResult(
                is_eligible=False,
                schedule_id=schedule.schedule_id,
                goal_id=schedule.goal_id,
                current_status=schedule.status,
                next_status=schedule.status,
                calculated_next_run_at=schedule.next_run_at,
                reason=f"Schedule status is {schedule.status.value}",
            )

        # 2. Max iterations check
        if (
            schedule.max_iterations is not None
            and schedule.iterations_count >= schedule.max_iterations
        ):
            return EvaluationResult(
                is_eligible=False,
                schedule_id=schedule.schedule_id,
                goal_id=schedule.goal_id,
                current_status=schedule.status,
                next_status=ScheduleStatus.COMPLETED,
                calculated_next_run_at=None,
                reason="Max iterations limit reached",
            )

        # 3. Type-specific evaluation
        if schedule.schedule_type == ScheduleType.ONE_SHOT:
            if schedule.iterations_count > 0:
                return EvaluationResult(
                    is_eligible=False,
                    schedule_id=schedule.schedule_id,
                    goal_id=schedule.goal_id,
                    current_status=schedule.status,
                    next_status=ScheduleStatus.COMPLETED,
                    calculated_next_run_at=None,
                    reason="ONE_SHOT schedule already executed",
                )
            if schedule.next_run_at and schedule.next_run_at > ref_iso:
                return EvaluationResult(
                    is_eligible=False,
                    schedule_id=schedule.schedule_id,
                    goal_id=schedule.goal_id,
                    current_status=schedule.status,
                    next_status=schedule.status,
                    calculated_next_run_at=schedule.next_run_at,
                    reason=f"ONE_SHOT target time {schedule.next_run_at} is in the future",
                )
            next_run = self.compute_next_run_at(schedule, from_timestamp=ref_iso)
            return EvaluationResult(
                is_eligible=True,
                schedule_id=schedule.schedule_id,
                goal_id=schedule.goal_id,
                current_status=schedule.status,
                next_status=ScheduleStatus.COMPLETED,
                calculated_next_run_at=next_run,
                reason="ONE_SHOT schedule is eligible for immediate single execution",
            )

        if schedule.schedule_type == ScheduleType.CONTINUOUS:
            next_run = self.compute_next_run_at(schedule, from_timestamp=ref_iso)
            return EvaluationResult(
                is_eligible=True,
                schedule_id=schedule.schedule_id,
                goal_id=schedule.goal_id,
                current_status=schedule.status,
                next_status=schedule.status,
                calculated_next_run_at=next_run,
                reason="CONTINUOUS schedule is eligible for on-demand execution",
            )

        # INTERVAL or CRON
        if schedule.next_run_at and schedule.next_run_at > ref_iso:
            return EvaluationResult(
                is_eligible=False,
                schedule_id=schedule.schedule_id,
                goal_id=schedule.goal_id,
                current_status=schedule.status,
                next_status=schedule.status,
                calculated_next_run_at=schedule.next_run_at,
                reason=f"Scheduled trigger time {schedule.next_run_at} has not arrived yet",
            )

        next_run = self.compute_next_run_at(schedule, from_timestamp=ref_iso)
        next_status = (
            ScheduleStatus.COMPLETED
            if (
                schedule.max_iterations is not None
                and (schedule.iterations_count + 1) >= schedule.max_iterations
            )
            else schedule.status
        )

        return EvaluationResult(
            is_eligible=True,
            schedule_id=schedule.schedule_id,
            goal_id=schedule.goal_id,
            current_status=schedule.status,
            next_status=next_status,
            calculated_next_run_at=next_run,
            reason=f"{schedule.schedule_type.value} schedule is due and eligible",
        )

    def compute_next_run_at(
        self,
        schedule: TemporalSchedule,
        from_timestamp: str | None = None,
    ) -> str | None:
        """Computes the next target UTC ISO timestamp for a schedule after execution."""
        if schedule.schedule_type == ScheduleType.ONE_SHOT:
            return None

        from_dt = _parse_utc_iso(from_timestamp)

        if schedule.schedule_type == ScheduleType.CONTINUOUS:
            return _format_utc_iso(from_dt)

        if schedule.schedule_type == ScheduleType.INTERVAL:
            try:
                seconds = float(schedule.expression.strip())
                if seconds <= 0:
                    seconds = 60.0
            except Exception:
                seconds = 60.0

            # Jump-to-future: calculate next interval relative to execution timestamp from_dt
            next_dt = from_dt + timedelta(seconds=seconds)
            return _format_utc_iso(next_dt)

        if schedule.schedule_type == ScheduleType.CRON:
            next_cron_dt = compute_next_cron_time(schedule.expression, from_dt)
            return _format_utc_iso(next_cron_dt)

        return None
