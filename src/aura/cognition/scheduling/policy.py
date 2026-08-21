from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any

from aura.config import ConfigurationManager
from aura.events import EventBus, RuntimeActivityLevelChanged, RuntimePolicyChanged
from aura.logging import get_logger

from .clock import Clock, SystemClock

logger = get_logger("PolicyAdaptationEngine")


class ActivityLevel(str, Enum):
    """Operational activity level for autonomous execution."""

    NORMAL = "NORMAL"
    REDUCED = "REDUCED"
    SUSPENDED = "SUSPENDED"


class PriorityMode(str, Enum):
    """Execution priority mode determined by operational policy."""

    STANDARD = "STANDARD"
    THROTTLED = "THROTTLED"
    CRITICAL_ONLY = "CRITICAL_ONLY"


@dataclass(frozen=True)
class PolicyDecision:
    """Immutable decision emitted by PolicyAdaptationEngine."""

    effective_tick_interval_seconds: float
    activity_level: ActivityLevel
    priority_mode: PriorityMode
    reason: str
    timestamp: str
    policy_version: str = "1.0.0"


@dataclass
class SystemSignals:
    """Observable inputs passed to PolicyAdaptationEngine for policy calculation."""

    health_status: str = "HEALTHY"
    worker_thread_alive: bool = True
    failed_ticks: int = 0
    successful_ticks: int = 0
    skipped_overlapping_ticks: int = 0
    recovery_attempts: int = 0
    recovery_failures: int = 0
    uptime_seconds: float = 0.0
    pending_schedules_count: int = 0
    system_load_level: str = "NORMAL"


class PolicyAdaptationEngine:
    """Deterministic policy engine evaluating operational signals for runtime adaptation."""

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
        self._last_decision: PolicyDecision | None = None

    def _sanitize_float(self, value: Any, default: float, min_val: float, max_val: float) -> float:
        try:
            val = float(value)
            if math.isnan(val) or math.isinf(val):
                return default
            return max(min_val, min(val, max_val))
        except ValueError, TypeError:
            return default

    def evaluate_policy(
        self,
        signals: SystemSignals,
        configured_interval: float = 1.0,
        runtime_name: str = "AuraAutonomyRuntime",
    ) -> PolicyDecision:
        """Evaluates operational signals and returns an immutable PolicyDecision."""
        with self._lock:
            now_iso = self.clock.now_iso()

            adaptation_enabled = True
            min_interval = 0.05
            max_interval = 60.0
            reduced_multiplier = 2.0

            if self.config is not None:
                adaptation_enabled = self.config.get_typed(
                    "autonomy.adaptation_enabled", bool, True
                )
                min_interval = self._sanitize_float(
                    self.config.get_typed("autonomy.min_tick_interval_seconds", float, 0.05),
                    default=0.05,
                    min_val=0.01,
                    max_val=10.0,
                )
                max_interval = self._sanitize_float(
                    self.config.get_typed("autonomy.max_tick_interval_seconds", float, 60.0),
                    default=60.0,
                    min_val=min_interval,
                    max_val=300.0,
                )
                reduced_multiplier = self._sanitize_float(
                    self.config.get_typed("autonomy.reduced_activity_multiplier", float, 2.0),
                    default=2.0,
                    min_val=1.0,
                    max_val=10.0,
                )

            sane_configured = self._sanitize_float(
                configured_interval, default=1.0, min_val=0.05, max_val=300.0
            )

            if not adaptation_enabled:
                decision = PolicyDecision(
                    effective_tick_interval_seconds=sane_configured,
                    activity_level=ActivityLevel.NORMAL,
                    priority_mode=PriorityMode.STANDARD,
                    reason="adaptation_disabled",
                    timestamp=now_iso,
                )
                self._last_decision = decision
                return decision

            # Rule 1: STOPPED or excessive recovery failures -> SUSPENDED
            if (
                signals.health_status.upper() == "STOPPED"
                or not signals.worker_thread_alive
                or signals.recovery_failures > 0
            ):
                activity = ActivityLevel.SUSPENDED
                priority = PriorityMode.CRITICAL_ONLY
                calc_interval = max(sane_configured * 5.0, 10.0)
                reason = f"suspended_due_to_health:{signals.health_status}"

            # Rule 2: DEGRADED or high load or tick failures -> REDUCED
            elif (
                signals.health_status.upper() == "DEGRADED"
                or signals.system_load_level.upper() in {"HIGH", "CRITICAL"}
                or signals.failed_ticks > 5
                or signals.skipped_overlapping_ticks > 10
                or signals.recovery_attempts > 0
            ):
                activity = ActivityLevel.REDUCED
                priority = PriorityMode.THROTTLED
                calc_interval = sane_configured * reduced_multiplier
                reason = f"reduced_due_to_degraded_or_load:{signals.system_load_level}"

            # Rule 3: Healthy & normal operating conditions -> NORMAL
            else:
                activity = ActivityLevel.NORMAL
                priority = PriorityMode.STANDARD
                calc_interval = sane_configured
                reason = "healthy_normal_operation"

            effective_interval = self._sanitize_float(
                calc_interval,
                default=sane_configured,
                min_val=min_interval,
                max_val=max_interval,
            )

            decision = PolicyDecision(
                effective_tick_interval_seconds=effective_interval,
                activity_level=activity,
                priority_mode=priority,
                reason=reason,
                timestamp=now_iso,
            )

            prev = self._last_decision
            if prev is not None and (
                prev.activity_level != decision.activity_level
                or prev.effective_tick_interval_seconds != decision.effective_tick_interval_seconds
            ):
                if self.event_bus is not None:
                    try:
                        self.event_bus.publish(
                            RuntimePolicyChanged(
                                runtime_name=runtime_name,
                                previous_activity_level=prev.activity_level.value,
                                new_activity_level=decision.activity_level.value,
                                effective_tick_interval=decision.effective_tick_interval_seconds,
                                reason=reason,
                            )
                        )
                        if prev.activity_level != decision.activity_level:
                            self.event_bus.publish(
                                RuntimeActivityLevelChanged(
                                    runtime_name=runtime_name,
                                    previous_level=prev.activity_level.value,
                                    new_level=decision.activity_level.value,
                                    reason=reason,
                                )
                            )
                    except Exception as exc:
                        logger.warning(f"Failed to publish policy change event: {exc}")

            self._last_decision = decision
            return decision
