from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from aura.config import ConfigurationManager
from aura.events import (
    AutonomyScopeChanged,
    CircuitBreakerReset,
    CircuitBreakerTripped,
    EventBus,
    GovernanceExecutionBlocked,
)
from aura.logging import get_logger

from .clock import Clock, SystemClock

logger = get_logger("RuntimeGovernanceEngine")


class AutonomyScope(str, Enum):
    """Operational permission scope for continuous autonomous execution."""

    UNRESTRICTED = "UNRESTRICTED"
    READ_ONLY = "READ_ONLY"
    SANDBOXED = "SANDBOXED"
    DISABLED = "DISABLED"


class CircuitState(str, Enum):
    """Circuit breaker operational state."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass(frozen=True)
class GovernancePolicy:
    """Immutable configuration rules for governance and safeguards."""

    scope: AutonomyScope = AutonomyScope.UNRESTRICTED
    circuit_breaker_enabled: bool = True
    failure_threshold: int = 5
    cooloff_seconds: float = 60.0
    rate_limit_max_calls_per_minute: int = 60
    min_action_cooldown_seconds: float = 0.0
    blocked_categories: tuple[str, ...] = ()


@dataclass(frozen=True)
class GovernanceDecision:
    """Immutable evaluation decision emitted by RuntimeGovernanceEngine."""

    allowed: bool
    reason: str
    scope: AutonomyScope
    circuit_state: CircuitState
    timestamp: str


@dataclass(frozen=True)
class GovernanceStatusSnapshot:
    """Immutable diagnostics snapshot of runtime governance status."""

    scope: AutonomyScope
    governance_enabled: bool
    active_circuits_count: int
    tripped_circuits: tuple[str, ...]
    total_evaluations: int
    allowed_evaluations: int
    blocked_evaluations: int
    last_blocked_at: str | None
    last_blocked_reason: str | None


@dataclass
class _CircuitRecord:
    failure_count: int = 0
    circuit_state: CircuitState = CircuitState.CLOSED
    tripped_at: datetime | None = None


class RuntimeGovernanceEngine:
    """Thread-safe runtime governance, safeguards, and bounded autonomy engine."""

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

        self._scope: AutonomyScope = AutonomyScope.UNRESTRICTED
        self._circuits: dict[str, _CircuitRecord] = {}
        self._call_history: list[datetime] = []

        self._total_evaluations: int = 0
        self._allowed_evaluations: int = 0
        self._blocked_evaluations: int = 0
        self._last_blocked_at: str | None = None
        self._last_blocked_reason: str | None = None

        self._apply_config()

    def _apply_config(self) -> None:
        if self.config is not None:
            raw_scope = self.config.get_typed(
                "autonomy.authority_scope", str, AutonomyScope.UNRESTRICTED.value
            )
            try:
                self._scope = AutonomyScope(raw_scope.upper())
            except ValueError:
                self._scope = AutonomyScope.UNRESTRICTED

    def get_scope(self) -> AutonomyScope:
        with self._lock:
            return self._scope

    def set_authority_scope(
        self, scope: AutonomyScope | str, reason: str = "manual_update"
    ) -> None:
        """Dynamically updates the operational authority scope."""
        with self._lock:
            old_scope = self._scope
            if isinstance(scope, str):
                try:
                    new_scope = AutonomyScope(scope.upper())
                except ValueError:
                    logger.warning(f"Invalid AutonomyScope '{scope}', ignoring update.")
                    return
            else:
                new_scope = scope

            if old_scope != new_scope:
                self._scope = new_scope
                logger.info(f"AutonomyScope changed: {old_scope.value} -> {new_scope.value}")
                if self.event_bus:
                    try:
                        self.event_bus.publish(
                            AutonomyScopeChanged(
                                runtime_name="AuraAutonomyRuntime",
                                previous_scope=old_scope.value,
                                new_scope=new_scope.value,
                                reason=reason,
                            )
                        )
                    except Exception as exc:
                        logger.warning(f"Failed to publish AutonomyScopeChanged event: {exc}")

    def evaluate_action(
        self,
        action_id: str,
        is_mutating: bool = True,
        category: str | None = None,
    ) -> GovernanceDecision:
        """Evaluates whether an action is allowed to execute under governance rules."""
        with self._lock:
            now_iso = self.clock.now_iso()
            self._total_evaluations += 1

            governance_enabled = True
            circuit_breaker_enabled = True
            cooloff_seconds = 60.0
            rate_limit_max = 60

            if self.config is not None:
                governance_enabled = self.config.get_typed(
                    "autonomy.governance_enabled", bool, True
                )
                circuit_breaker_enabled = self.config.get_typed(
                    "autonomy.circuit_breaker_enabled", bool, True
                )
                cooloff_seconds = self.config.get_typed(
                    "autonomy.circuit_cooloff_seconds", float, 60.0
                )
                rate_limit_max = self.config.get_typed(
                    "autonomy.rate_limit_max_calls_per_minute", int, 60
                )

            if not governance_enabled:
                self._allowed_evaluations += 1
                return GovernanceDecision(
                    allowed=True,
                    reason="governance_disabled",
                    scope=self._scope,
                    circuit_state=CircuitState.CLOSED,
                    timestamp=now_iso,
                )

            # Rule 1: AutonomyScope permissions check
            if self._scope == AutonomyScope.DISABLED:
                return self._block_decision(
                    action_id, "governance_scope_disabled", CircuitState.CLOSED, now_iso
                )
            elif self._scope == AutonomyScope.READ_ONLY and is_mutating:
                return self._block_decision(
                    action_id, "governance_scope_read_only", CircuitState.CLOSED, now_iso
                )
            elif self._scope == AutonomyScope.SANDBOXED and (
                category and category.upper() in {"EXTERNAL", "RESTRICTED", "DESTRUCTIVE"}
            ):
                return self._block_decision(
                    action_id, "governance_scope_sandboxed", CircuitState.CLOSED, now_iso
                )

            # Rule 2: Circuit Breaker check
            circuit_state = CircuitState.CLOSED
            if circuit_breaker_enabled:
                rec = self._circuits.get(action_id)
                if rec is not None:
                    if rec.circuit_state == CircuitState.OPEN:
                        now_dt = datetime.fromisoformat(self.clock.now_iso())
                        if (
                            rec.tripped_at is not None
                            and (now_dt - rec.tripped_at).total_seconds() >= cooloff_seconds
                        ):
                            rec.circuit_state = CircuitState.HALF_OPEN
                            circuit_state = CircuitState.HALF_OPEN
                            logger.info(
                                f"Circuit breaker for '{action_id}' transitioned to HALF_OPEN."
                            )
                        else:
                            return self._block_decision(
                                action_id, "circuit_breaker_open", CircuitState.OPEN, now_iso
                            )
                    else:
                        circuit_state = rec.circuit_state

            # Rule 3: Rate limiting check (sliding window 60s)
            now_dt = datetime.fromisoformat(self.clock.now_iso())
            self._call_history = [
                t for t in self._call_history if (now_dt - t).total_seconds() <= 60.0
            ]
            if len(self._call_history) >= rate_limit_max:
                return self._block_decision(
                    action_id, "rate_limit_exceeded", circuit_state, now_iso
                )

            self._call_history.append(now_dt)
            self._allowed_evaluations += 1
            return GovernanceDecision(
                allowed=True,
                reason="authorized",
                scope=self._scope,
                circuit_state=circuit_state,
                timestamp=now_iso,
            )

    def _block_decision(
        self,
        action_id: str,
        reason: str,
        circuit_state: CircuitState,
        timestamp: str,
    ) -> GovernanceDecision:
        self._blocked_evaluations += 1
        self._last_blocked_at = timestamp
        self._last_blocked_reason = reason
        logger.info(f"Governance blocked execution of '{action_id}': {reason}")

        if self.event_bus:
            try:
                self.event_bus.publish(
                    GovernanceExecutionBlocked(
                        action_id=action_id,
                        reason=reason,
                        scope=self._scope.value,
                        circuit_state=circuit_state.value,
                    )
                )
            except Exception as exc:
                logger.warning(f"Failed to publish GovernanceExecutionBlocked event: {exc}")

        return GovernanceDecision(
            allowed=False,
            reason=reason,
            scope=self._scope,
            circuit_state=circuit_state,
            timestamp=timestamp,
        )

    def record_action_outcome(
        self,
        action_id: str,
        success: bool,
        error: str | None = None,
    ) -> None:
        """Records the outcome of an action, updating circuit breaker counters."""
        with self._lock:
            failure_threshold = 5
            cooloff_seconds = 60.0
            if self.config is not None:
                failure_threshold = self.config.get_typed(
                    "autonomy.circuit_failure_threshold", int, 5
                )
                cooloff_seconds = self.config.get_typed(
                    "autonomy.circuit_cooloff_seconds", float, 60.0
                )

            rec = self._circuits.setdefault(action_id, _CircuitRecord())

            if success:
                if rec.circuit_state in {CircuitState.OPEN, CircuitState.HALF_OPEN}:
                    rec.circuit_state = CircuitState.CLOSED
                    rec.failure_count = 0
                    rec.tripped_at = None
                    logger.info(f"Circuit breaker for '{action_id}' reset to CLOSED on success.")
                    if self.event_bus:
                        try:
                            self.event_bus.publish(
                                CircuitBreakerReset(
                                    target_id=action_id,
                                    reason="action_success_recovery",
                                )
                            )
                        except Exception as exc:
                            logger.warning(f"Failed to publish CircuitBreakerReset event: {exc}")
                else:
                    rec.failure_count = 0
            else:
                rec.failure_count += 1
                if (
                    rec.failure_count >= failure_threshold
                    and rec.circuit_state != CircuitState.OPEN
                ):
                    rec.circuit_state = CircuitState.OPEN
                    rec.tripped_at = datetime.fromisoformat(self.clock.now_iso())
                    logger.warning(
                        f"Circuit breaker tripped OPEN for '{action_id}' after "
                        f"{rec.failure_count} failures."
                    )
                    if self.event_bus:
                        try:
                            self.event_bus.publish(
                                CircuitBreakerTripped(
                                    target_id=action_id,
                                    failure_count=rec.failure_count,
                                    cooloff_seconds=cooloff_seconds,
                                    reason=f"failure_threshold_exceeded:{error or 'unknown'}",
                                )
                            )
                        except Exception as exc:
                            logger.warning(f"Failed to publish CircuitBreakerTripped event: {exc}")

    def trip_circuit(self, target_id: str, reason: str = "manual_override") -> None:
        """Manually trips a circuit breaker to OPEN."""
        with self._lock:
            cooloff_seconds = 60.0
            if self.config is not None:
                cooloff_seconds = self.config.get_typed(
                    "autonomy.circuit_cooloff_seconds", float, 60.0
                )
            rec = self._circuits.setdefault(target_id, _CircuitRecord())
            rec.circuit_state = CircuitState.OPEN
            rec.tripped_at = datetime.fromisoformat(self.clock.now_iso())
            logger.warning(f"Circuit breaker manually tripped for '{target_id}': {reason}")
            if self.event_bus:
                try:
                    self.event_bus.publish(
                        CircuitBreakerTripped(
                            target_id=target_id,
                            failure_count=rec.failure_count,
                            cooloff_seconds=cooloff_seconds,
                            reason=reason,
                        )
                    )
                except Exception as exc:
                    logger.warning(f"Failed to publish CircuitBreakerTripped event: {exc}")

    def reset_circuit(self, target_id: str, reason: str = "manual_reset") -> None:
        """Manually resets a circuit breaker to CLOSED."""
        with self._lock:
            rec = self._circuits.setdefault(target_id, _CircuitRecord())
            rec.circuit_state = CircuitState.CLOSED
            rec.failure_count = 0
            rec.tripped_at = None
            logger.info(f"Circuit breaker manually reset for '{target_id}': {reason}")
            if self.event_bus:
                try:
                    self.event_bus.publish(CircuitBreakerReset(target_id=target_id, reason=reason))
                except Exception as exc:
                    logger.warning(f"Failed to publish CircuitBreakerReset event: {exc}")

    def get_circuit_state(self, target_id: str) -> CircuitState:
        with self._lock:
            rec = self._circuits.get(target_id)
            return rec.circuit_state if rec is not None else CircuitState.CLOSED

    def get_governance_snapshot(self) -> GovernanceStatusSnapshot:
        """Returns an immutable GovernanceStatusSnapshot for runtime diagnostics."""
        with self._lock:
            governance_enabled = True
            if self.config is not None:
                governance_enabled = self.config.get_typed(
                    "autonomy.governance_enabled", bool, True
                )

            tripped = tuple(
                k
                for k, v in self._circuits.items()
                if v.circuit_state in {CircuitState.OPEN, CircuitState.HALF_OPEN}
            )

            return GovernanceStatusSnapshot(
                scope=self._scope,
                governance_enabled=governance_enabled,
                active_circuits_count=len(tripped),
                tripped_circuits=tripped,
                total_evaluations=self._total_evaluations,
                allowed_evaluations=self._allowed_evaluations,
                blocked_evaluations=self._blocked_evaluations,
                last_blocked_at=self._last_blocked_at,
                last_blocked_reason=self._last_blocked_reason,
            )
