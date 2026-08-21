from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from aura.config import ConfigurationManager
from aura.events import (
    EventBus,
    RuntimePolicyConflictDetected,
    RuntimePolicyDecisionMade,
    RuntimeTaskCancelled,
    RuntimeTaskDeferred,
    RuntimeTaskPriorityChanged,
)
from aura.logging import get_logger

from .clock import Clock, SystemClock
from .models import TemporalSchedule

logger = get_logger("RuntimePolicyEngine")


class PolicyPriority(str, Enum):
    """Operational task execution priority."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"
    BACKGROUND = "BACKGROUND"

    @property
    def weight(self) -> float:
        weights = {
            PolicyPriority.CRITICAL: 100.0,
            PolicyPriority.HIGH: 75.0,
            PolicyPriority.NORMAL: 50.0,
            PolicyPriority.LOW: 25.0,
            PolicyPriority.BACKGROUND: 10.0,
        }
        return weights[self]


class PolicyAction(str, Enum):
    """Operational action decided by RuntimePolicyEngine."""

    ALLOW = "ALLOW"
    DEFER = "DEFER"
    CANCEL = "CANCEL"
    REPLACE = "REPLACE"
    BLOCK = "BLOCK"


class ConflictType(str, Enum):
    """Types of operational task conflicts."""

    RESOURCE_CONFLICT = "RESOURCE_CONFLICT"
    MUTUAL_EXCLUSION = "MUTUAL_EXCLUSION"
    HIGHER_PRIORITY = "HIGHER_PRIORITY"
    DEADLINE_EXPIRED = "DEADLINE_EXPIRED"
    DUPLICATE = "DUPLICATE"
    GOVERNANCE_CONFLICT = "GOVERNANCE_CONFLICT"


@dataclass(frozen=True)
class PolicyConflict:
    """Immutable record of an operational conflict between tasks."""

    conflict_id: str
    conflict_type: ConflictType
    winning_task_id: str
    losing_task_id: str
    resource_id: str | None
    reason: str
    timestamp: str


@dataclass(frozen=True)
class RuntimePolicyDecision:
    """Immutable decision emitted by RuntimePolicyEngine."""

    allowed: bool
    action: PolicyAction
    reason: str
    effective_priority: float
    base_priority: PolicyPriority
    conflict: PolicyConflict | None
    timestamp: str


PolicyDecision = RuntimePolicyDecision


@dataclass(frozen=True)
class PolicyStatusSnapshot:
    """Immutable diagnostics snapshot of RuntimePolicyEngine operational state."""

    policy_enabled: bool
    total_evaluations: int
    allowed_count: int
    deferred_count: int
    cancelled_count: int
    blocked_count: int
    conflicts_detected_count: int
    deadlines_expired_count: int
    active_resource_locks: tuple[str, ...]
    waiting_tasks_count: int


def _parse_iso(ts: str) -> datetime:
    try:
        dt = datetime.fromisoformat(ts.strip())
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:
        return datetime.now(UTC)


class RuntimePolicyEngine:
    """Thread-safe deterministic policy, priority resolution & conflict management engine."""

    def __init__(
        self,
        clock: Clock | None = None,
        event_bus: EventBus | None = None,
        config: ConfigurationManager | None = None,
    ) -> None:
        self.clock = clock or SystemClock()
        self.event_bus = event_bus
        self.config = config
        self._lock = threading.RLock()

        # Operational state
        self._resource_locks: dict[str, str] = {}  # resource_id -> task_id
        self._task_resources: dict[str, set[str]] = {}  # task_id -> set of resource_ids
        self._task_priorities: dict[str, float] = {}  # task_id -> effective_priority
        self._active_tasks: dict[str, str] = {}  # dedup_key/goal_id -> task_id
        self._waiting_tasks: set[str] = set()

        # Telemetry counters
        self._total_evaluations: int = 0
        self._allowed_count: int = 0
        self._deferred_count: int = 0
        self._cancelled_count: int = 0
        self._blocked_count: int = 0
        self._conflicts_detected_count: int = 0
        self._deadlines_expired_count: int = 0

    def calculate_effective_priority(
        self,
        base_priority: PolicyPriority | str,
        created_at_iso: str,
        task_id: str | None = None,
    ) -> float:
        """Calculates effective priority incorporating deterministic aging boost."""
        with self._lock:
            if isinstance(base_priority, str):
                try:
                    p_enum = PolicyPriority(base_priority.upper())
                except ValueError:
                    p_enum = PolicyPriority.NORMAL
            else:
                p_enum = base_priority

            base_weight = p_enum.weight

            aging_enabled = True
            aging_rate = 1.0  # boost per minute
            max_boost = 50.0

            if self.config is not None:
                aging_enabled = self.config.get_typed("autonomy.priority_aging_enabled", bool, True)
                aging_rate = self.config.get_typed(
                    "autonomy.priority_aging_rate_per_minute", float, 1.0
                )
                max_boost = self.config.get_typed("autonomy.max_aging_boost", float, 50.0)

            if not aging_enabled:
                return base_weight

            now_dt = _parse_iso(self.clock.now_iso())
            created_dt = _parse_iso(created_at_iso)
            elapsed_seconds = max(0.0, (now_dt - created_dt).total_seconds())
            elapsed_minutes = elapsed_seconds / 60.0

            boost = min(max_boost, max(0.0, elapsed_minutes * aging_rate))
            effective = base_weight + boost

            if task_id:
                prev_eff = self._task_priorities.get(task_id, base_weight)
                if effective > prev_eff + 5.0 and self.event_bus:
                    try:
                        self.event_bus.publish(
                            RuntimeTaskPriorityChanged(
                                task_id=task_id,
                                previous_priority=prev_eff,
                                new_priority=effective,
                                reason="priority_aging_boost",
                            )
                        )
                    except Exception as exc:
                        logger.warning(f"Failed to publish RuntimeTaskPriorityChanged: {exc}")
                self._task_priorities[task_id] = effective

            return effective

    def evaluate_schedule(
        self,
        sched: TemporalSchedule,
        goal: Any | None = None,
    ) -> PolicyDecision:
        """Evaluates a schedule against policy rules, priority aging, deadlines, and conflicts."""
        with self._lock:
            now_iso = self.clock.now_iso()
            self._total_evaluations += 1

            policy_enabled = True
            deadline_enabled = True
            conflict_enabled = True
            default_p_str = "NORMAL"

            if self.config is not None:
                policy_enabled = self.config.get_typed(
                    "autonomy.policy_resolution_enabled", bool, True
                )
                deadline_enabled = self.config.get_typed(
                    "autonomy.deadline_enforcement_enabled", bool, True
                )
                conflict_enabled = self.config.get_typed(
                    "autonomy.conflict_resolution_enabled", bool, True
                )
                default_p_str = self.config.get_typed("autonomy.default_priority", str, "NORMAL")

            # Extract priority from metadata or goal
            raw_priority = sched.metadata.get("priority")
            if not raw_priority and goal is not None:
                raw_priority = getattr(goal, "priority", None)
            if not raw_priority:
                raw_priority = default_p_str

            try:
                base_priority = PolicyPriority(str(raw_priority).upper())
            except ValueError:
                base_priority = PolicyPriority.NORMAL

            effective_priority = self.calculate_effective_priority(
                base_priority=base_priority,
                created_at_iso=sched.created_at,
                task_id=sched.schedule_id,
            )

            if not policy_enabled:
                self._allowed_count += 1
                return PolicyDecision(
                    allowed=True,
                    action=PolicyAction.ALLOW,
                    reason="policy_resolution_disabled",
                    effective_priority=effective_priority,
                    base_priority=base_priority,
                    conflict=None,
                    timestamp=now_iso,
                )

            # Rule 1: Deadline Expiration Check
            deadline_iso = sched.metadata.get("deadline_at") or sched.metadata.get("deadline_iso")
            if deadline_enabled and deadline_iso:
                now_dt = _parse_iso(now_iso)
                deadline_dt = _parse_iso(str(deadline_iso))
                if now_dt > deadline_dt:
                    self._cancelled_count += 1
                    self._deadlines_expired_count += 1
                    conflict = PolicyConflict(
                        conflict_id=f"conf_{uuid.uuid4().hex[:8]}",
                        conflict_type=ConflictType.DEADLINE_EXPIRED,
                        winning_task_id="NONE",
                        losing_task_id=sched.schedule_id,
                        resource_id=None,
                        reason=f"Deadline expired at {deadline_iso}",
                        timestamp=now_iso,
                    )
                    self._publish_decision_events(
                        sched.schedule_id,
                        PolicyAction.CANCEL,
                        "deadline_expired",
                        conflict,
                        effective_priority,
                    )
                    return PolicyDecision(
                        allowed=False,
                        action=PolicyAction.CANCEL,
                        reason="deadline_expired",
                        effective_priority=effective_priority,
                        base_priority=base_priority,
                        conflict=conflict,
                        timestamp=now_iso,
                    )

            # Rule 2: Deduplication Check
            dedup_key = sched.metadata.get("dedup_key") or sched.goal_id
            active_task_id = self._active_tasks.get(dedup_key)
            if conflict_enabled and active_task_id and active_task_id != sched.schedule_id:
                self._cancelled_count += 1
                self._conflicts_detected_count += 1
                conflict = PolicyConflict(
                    conflict_id=f"conf_{uuid.uuid4().hex[:8]}",
                    conflict_type=ConflictType.DUPLICATE,
                    winning_task_id=active_task_id,
                    losing_task_id=sched.schedule_id,
                    resource_id=None,
                    reason=(
                        f"Duplicate execution key '{dedup_key}' "
                        f"active under task '{active_task_id}'"
                    ),
                    timestamp=now_iso,
                )
                self._publish_decision_events(
                    sched.schedule_id,
                    PolicyAction.CANCEL,
                    "duplicate_task_execution",
                    conflict,
                    effective_priority,
                )
                return PolicyDecision(
                    allowed=False,
                    action=PolicyAction.CANCEL,
                    reason="duplicate_task_execution",
                    effective_priority=effective_priority,
                    base_priority=base_priority,
                    conflict=conflict,
                    timestamp=now_iso,
                )

            # Rule 3: Resource Contention & Mutex Locks
            required_resources = sched.metadata.get("required_resources", [])
            if isinstance(required_resources, str):
                required_resources = [required_resources]

            if conflict_enabled and required_resources:
                for res_id in required_resources:
                    locking_task = self._resource_locks.get(res_id)
                    if locking_task and locking_task != sched.schedule_id:
                        locking_priority = self._task_priorities.get(locking_task, 50.0)
                        if effective_priority <= locking_priority:
                            self._deferred_count += 1
                            self._conflicts_detected_count += 1
                            self._waiting_tasks.add(sched.schedule_id)
                            conflict = PolicyConflict(
                                conflict_id=f"conf_{uuid.uuid4().hex[:8]}",
                                conflict_type=ConflictType.RESOURCE_CONFLICT,
                                winning_task_id=locking_task,
                                losing_task_id=sched.schedule_id,
                                resource_id=res_id,
                                reason=(
                                    f"Resource '{res_id}' locked by task "
                                    f"'{locking_task}' (p={locking_priority:.1f})"
                                ),
                                timestamp=now_iso,
                            )
                            self._publish_decision_events(
                                sched.schedule_id,
                                PolicyAction.DEFER,
                                "resource_conflict",
                                conflict,
                                effective_priority,
                            )
                            return PolicyDecision(
                                allowed=False,
                                action=PolicyAction.DEFER,
                                reason=f"resource_conflict:{res_id}",
                                effective_priority=effective_priority,
                                base_priority=base_priority,
                                conflict=conflict,
                                timestamp=now_iso,
                            )
                        else:
                            # Higher priority task pre-empts lower priority lock
                            logger.info(
                                f"Task '{sched.schedule_id}' (p={effective_priority:.1f}) "
                                f"pre-empting resource '{res_id}' from task "
                                f"'{locking_task}' (p={locking_priority:.1f})"
                            )

                # Acquire resource locks for allowed execution
                for res_id in required_resources:
                    self._resource_locks[res_id] = sched.schedule_id
                    self._task_resources.setdefault(sched.schedule_id, set()).add(res_id)

            # Register as active task
            self._active_tasks[dedup_key] = sched.schedule_id
            self._waiting_tasks.discard(sched.schedule_id)
            self._allowed_count += 1

            self._publish_decision_events(
                sched.schedule_id,
                PolicyAction.ALLOW,
                "authorized_by_policy",
                None,
                effective_priority,
            )
            return PolicyDecision(
                allowed=True,
                action=PolicyAction.ALLOW,
                reason="authorized_by_policy",
                effective_priority=effective_priority,
                base_priority=base_priority,
                conflict=None,
                timestamp=now_iso,
            )

    def _publish_decision_events(
        self,
        task_id: str,
        action: PolicyAction,
        reason: str,
        conflict: PolicyConflict | None,
        effective_priority: float,
    ) -> None:
        if self.event_bus:
            try:
                self.event_bus.publish(
                    RuntimePolicyDecisionMade(
                        task_id=task_id,
                        action=action.value,
                        reason=reason,
                        effective_priority=effective_priority,
                        decision_timestamp=self.clock.now_iso(),
                    )
                )
                if conflict is not None:
                    self.event_bus.publish(
                        RuntimePolicyConflictDetected(
                            conflict_id=conflict.conflict_id,
                            conflict_type=conflict.conflict_type.value,
                            winning_task_id=conflict.winning_task_id,
                            losing_task_id=conflict.losing_task_id,
                            reason=conflict.reason,
                        )
                    )
                if action == PolicyAction.DEFER:
                    self.event_bus.publish(
                        RuntimeTaskDeferred(
                            task_id=task_id,
                            reason=reason,
                            effective_priority=effective_priority,
                        )
                    )
                elif action == PolicyAction.CANCEL:
                    self.event_bus.publish(
                        RuntimeTaskCancelled(
                            task_id=task_id,
                            reason=reason,
                        )
                    )
            except Exception as exc:
                logger.warning(f"Failed to publish policy events: {exc}")

    def record_task_completion(self, task_id: str, success: bool = True) -> None:
        """Releases resource locks and active tasks held by task_id upon completion."""
        with self._lock:
            # Release resource locks
            res_set = self._task_resources.pop(task_id, set())
            for res_id in res_set:
                if self._resource_locks.get(res_id) == task_id:
                    del self._resource_locks[res_id]

            # Remove from active tasks
            to_remove = [k for k, v in self._active_tasks.items() if v == task_id]
            for k in to_remove:
                del self._active_tasks[k]

            self._waiting_tasks.discard(task_id)
            self._task_priorities.pop(task_id, None)

    def get_policy_snapshot(self) -> PolicyStatusSnapshot:
        """Returns an immutable PolicyStatusSnapshot for diagnostics."""
        with self._lock:
            policy_enabled = True
            if self.config is not None:
                policy_enabled = self.config.get_typed(
                    "autonomy.policy_resolution_enabled", bool, True
                )

            return PolicyStatusSnapshot(
                policy_enabled=policy_enabled,
                total_evaluations=self._total_evaluations,
                allowed_count=self._allowed_count,
                deferred_count=self._deferred_count,
                cancelled_count=self._cancelled_count,
                blocked_count=self._blocked_count,
                conflicts_detected_count=self._conflicts_detected_count,
                deadlines_expired_count=self._deadlines_expired_count,
                active_resource_locks=tuple(self._resource_locks.keys()),
                waiting_tasks_count=len(self._waiting_tasks),
            )
