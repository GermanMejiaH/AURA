from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class ScheduleType(str, Enum):
    ONE_SHOT = "ONE_SHOT"
    INTERVAL = "INTERVAL"
    CRON = "CRON"
    CONTINUOUS = "CONTINUOUS"


class ScheduleStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


def _normalize_iso_timestamp(ts: str | None) -> str | None:
    """Normalizes an ISO timestamp string to UTC ISO 8601 representation."""
    if not ts or not ts.strip():
        return None
    try:
        dt = datetime.fromisoformat(ts.strip())
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        else:
            dt = dt.astimezone(UTC)
        return dt.isoformat()
    except Exception:
        return ts.strip()


def _now_utc_iso() -> str:
    """Returns the current UTC time as an ISO 8601 string."""
    return datetime.now(UTC).isoformat()


@dataclass
class TemporalSchedule:
    """Domain model representing a temporal trigger schedule for a PersistentGoal."""

    goal_id: str
    schedule_type: ScheduleType = ScheduleType.ONE_SHOT
    schedule_id: str = field(default_factory=lambda: f"sched_{uuid.uuid4().hex[:8]}")
    status: ScheduleStatus = ScheduleStatus.ACTIVE
    expression: str = ""
    created_at: str = field(default_factory=_now_utc_iso)
    updated_at: str = field(default_factory=_now_utc_iso)
    last_run_at: str | None = None
    next_run_at: str | None = None
    max_iterations: int | None = None
    iterations_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.goal_id or not self.goal_id.strip():
            raise ValueError("TemporalSchedule goal_id cannot be empty.")
        if self.iterations_count < 0:
            raise ValueError("TemporalSchedule iterations_count cannot be negative.")
        if self.max_iterations is not None and self.max_iterations < 1:
            raise ValueError("TemporalSchedule max_iterations must be at least 1.")

        self.created_at = _normalize_iso_timestamp(self.created_at) or _now_utc_iso()
        self.updated_at = _normalize_iso_timestamp(self.updated_at) or _now_utc_iso()
        self.last_run_at = _normalize_iso_timestamp(self.last_run_at)
        self.next_run_at = _normalize_iso_timestamp(self.next_run_at)

    def set_status(self, new_status: ScheduleStatus) -> None:
        self.status = new_status
        self.updated_at = _now_utc_iso()

    def is_eligible(self, at_timestamp: str | None = None) -> bool:
        """Determines if the schedule is eligible for execution at given ISO timestamp."""
        if self.status != ScheduleStatus.ACTIVE:
            return False

        if self.max_iterations is not None and self.iterations_count >= self.max_iterations:
            return False

        if self.schedule_type == ScheduleType.CONTINUOUS:
            return True

        if not self.next_run_at:
            return True

        target_time = _normalize_iso_timestamp(at_timestamp) or _now_utc_iso()
        return self.next_run_at <= target_time

    def record_run(
        self,
        run_at: str | None = None,
        next_run_at: str | None = None,
    ) -> None:
        """Updates schedule state after execution run deterministically.

        Only ACTIVE schedules can record execution runs.
        """
        if self.status != ScheduleStatus.ACTIVE:
            return

        now_iso = _normalize_iso_timestamp(run_at) or _now_utc_iso()
        self.last_run_at = now_iso
        self.iterations_count += 1
        self.updated_at = now_iso

        if next_run_at is not None:
            self.next_run_at = _normalize_iso_timestamp(next_run_at)

        if self.schedule_type == ScheduleType.ONE_SHOT:
            self.status = ScheduleStatus.COMPLETED
        elif self.max_iterations is not None and self.iterations_count >= self.max_iterations:
            self.status = ScheduleStatus.COMPLETED
