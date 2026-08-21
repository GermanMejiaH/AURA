from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from aura.config import ConfigurationManager
from aura.events import (
    EventBus,
    RuntimeExecutionCancelled,
    RuntimeExecutionCompensated,
    RuntimeExecutionCompensating,
    RuntimeExecutionCompleted,
    RuntimeExecutionFailed,
    RuntimeExecutionRetrying,
    RuntimeExecutionRolledBack,
    RuntimeExecutionStarted,
    RuntimeExecutionTimedOut,
    RuntimeExecutionValidated,
)
from aura.logging import get_logger

from .clock import Clock, SystemClock
from .models import TemporalSchedule

logger = get_logger("RuntimeExecutionEngine")


class ExecutionState(str, Enum):
    """Deterministic states of an autonomous action execution lifecycle."""

    PENDING = "PENDING"
    PREPARING = "PREPARING"
    VALIDATING = "VALIDATING"
    EXECUTING = "EXECUTING"
    COMMITTING = "COMMITTING"
    COMMITTED = "COMMITTED"
    ROLLING_BACK = "ROLLING_BACK"
    ROLLED_BACK = "ROLLED_BACK"
    COMPENSATING = "COMPENSATING"
    COMPENSATED = "COMPENSATED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


class ExecutionFailureType(str, Enum):
    """Categories of operational execution failures."""

    TRANSIENT = "TRANSIENT"
    PERMANENT = "PERMANENT"
    VALIDATION = "VALIDATION"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    ROLLBACK_FAILURE = "ROLLBACK_FAILURE"
    COMPENSATION_FAILURE = "COMPENSATION_FAILURE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ExecutionContext:
    """Immutable execution context holding operational identity and constraints."""

    execution_id: str
    goal_id: str
    schedule_id: str
    idempotency_key: str
    started_at: str
    deadline_at: str | None = None
    timeout_seconds: float = 30.0
    attempt_number: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionResult:
    """Immutable result of an operational action execution cycle."""

    execution_id: str
    goal_id: str
    schedule_id: str
    idempotency_key: str
    success: bool
    state: ExecutionState
    attempt_number: int
    started_at: str
    completed_at: str
    error: str | None
    failure_type: ExecutionFailureType | None
    rollback_performed: bool
    compensation_performed: bool
    output: Any | None = None


@dataclass(frozen=True)
class RetryPolicy:
    """Configurable retry policy for execution failures."""

    max_attempts: int = 3
    backoff_seconds: float = 1.0
    retryable_failures: tuple[ExecutionFailureType, ...] = (
        ExecutionFailureType.TRANSIENT,
        ExecutionFailureType.TIMEOUT,
    )


@dataclass(frozen=True)
class ExecutionStatusSnapshot:
    """Immutable diagnostics snapshot of RuntimeExecutionEngine state."""

    execution_enabled: bool
    total_executions: int
    successful_executions: int
    failed_executions: int
    cancelled_executions: int
    timed_out_executions: int
    retry_count: int
    rollback_count: int
    compensation_count: int
    active_executions_count: int


class RuntimeAction:
    """Base class / contract for transactional actions executable by RuntimeExecutionEngine."""

    def __init__(
        self,
        action_id: str,
        name: str,
        is_idempotent: bool = True,
        execute_fn: Callable[[ExecutionContext], Any] | None = None,
        rollback_fn: Callable[[ExecutionContext], bool] | None = None,
        compensate_fn: Callable[[ExecutionContext], bool] | None = None,
    ) -> None:
        self.action_id = action_id
        self.name = name
        self.is_idempotent = is_idempotent
        self._execute_fn = execute_fn
        self._rollback_fn = rollback_fn
        self._compensate_fn = compensate_fn

    def validate(self, context: ExecutionContext) -> bool:
        """Validates action pre-conditions prior to execution."""
        return True

    def execute(self, context: ExecutionContext) -> Any:
        """Executes the core action logic."""
        if self._execute_fn:
            return self._execute_fn(context)
        return None

    def rollback(self, context: ExecutionContext) -> bool:
        """Rolls back side-effects performed during execution."""
        if self._rollback_fn:
            return self._rollback_fn(context)
        return True

    def compensate(self, context: ExecutionContext) -> bool:
        """Compensates side-effects when rollback is insufficient or failed."""
        if self._compensate_fn:
            return self._compensate_fn(context)
        return True


class ExecutionTransaction:
    """Tracks performed action steps for reverse-order rollback and compensation."""

    def __init__(self) -> None:
        self._steps: list[tuple[RuntimeAction, ExecutionContext]] = []

    def register_step(self, action: RuntimeAction, context: ExecutionContext) -> None:
        self._steps.append((action, context))

    def perform_rollback(self) -> tuple[bool, str | None]:
        """Rolls back performed steps in reverse order (stack order)."""
        errors: list[str] = []
        for action, ctx in reversed(self._steps):
            try:
                ok = action.rollback(ctx)
                if not ok:
                    errors.append(f"Rollback returned False for step '{action.action_id}'")
            except Exception as exc:
                errors.append(f"Rollback error for step '{action.action_id}': {exc}")
        if errors:
            return False, "; ".join(errors)
        return True, None

    def perform_compensation(self) -> tuple[bool, str | None]:
        """Compensates performed steps in reverse order when rollback fails."""
        errors: list[str] = []
        for action, ctx in reversed(self._steps):
            try:
                ok = action.compensate(ctx)
                if not ok:
                    errors.append(f"Compensation returned False for step '{action.action_id}'")
            except Exception as exc:
                errors.append(f"Compensation error for step '{action.action_id}': {exc}")
        if errors:
            return False, "; ".join(errors)
        return True, None


def _parse_iso(ts: str) -> datetime:
    try:
        dt = datetime.fromisoformat(ts.strip())
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:
        return datetime.now(UTC)


class RuntimeExecutionEngine:
    """Thread-safe transactional execution engine for autonomous actions."""

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
        self._active_executions: dict[str, ExecutionContext] = {}  # exec_id -> ctx
        self._active_idempotency: dict[str, str] = {}  # idempotency_key -> exec_id
        self._idempotency_store: dict[str, ExecutionResult] = {}  # idempotency_key -> result
        self._execution_history: list[ExecutionResult] = []
        self._execution_results: dict[str, ExecutionResult] = {}  # exec_id -> result

        # Telemetry counters
        self._total_executions: int = 0
        self._successful_executions: int = 0
        self._failed_executions: int = 0
        self._cancelled_executions: int = 0
        self._timed_out_executions: int = 0
        self._retry_count: int = 0
        self._rollback_count: int = 0
        self._compensation_count: int = 0

    def execute_schedule_action(
        self,
        sched: TemporalSchedule,
        goal: Any,
        goal_executor_fn: Callable[[], Any],
    ) -> ExecutionResult:
        """Helper to wrap and execute a goal cycle dispatch cleanly as a RuntimeAction."""
        dedup_key = (
            sched.metadata.get("idempotency_key")
            or f"sched:{sched.schedule_id}:{sched.iterations_count + 1}"
        )
        action = RuntimeAction(
            action_id=f"act_{sched.schedule_id}",
            name=f"ExecuteGoal_{sched.goal_id}",
            execute_fn=lambda ctx: goal_executor_fn(),
        )
        ctx = ExecutionContext(
            execution_id=f"exec_{uuid.uuid4().hex[:12]}",
            goal_id=sched.goal_id,
            schedule_id=sched.schedule_id,
            idempotency_key=dedup_key,
            started_at=self.clock.now_iso(),
            metadata=sched.metadata,
        )
        return self.execute(action, context=ctx)

    def execute(
        self,
        action: RuntimeAction | Callable[[ExecutionContext], Any],
        context: ExecutionContext | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> ExecutionResult:
        """Executes a RuntimeAction transactionally.

        Includes validation, retries, reverse-order rollback, and compensation.
        """
        with self._lock:
            now_iso = self.clock.now_iso()

            # Handle raw callable conversion to RuntimeAction
            if not isinstance(action, RuntimeAction):
                fn = action
                action = RuntimeAction(
                    action_id=f"act_{uuid.uuid4().hex[:8]}",
                    name="AnonymousAction",
                    execute_fn=fn,
                )

            if context is None:
                context = ExecutionContext(
                    execution_id=f"exec_{uuid.uuid4().hex[:12]}",
                    goal_id="unknown_goal",
                    schedule_id="unknown_schedule",
                    idempotency_key=f"idemp_{uuid.uuid4().hex[:8]}",
                    started_at=now_iso,
                )

            # Idempotency store check
            if context.idempotency_key in self._idempotency_store:
                cached_res = self._idempotency_store[context.idempotency_key]
                if cached_res.state in (ExecutionState.COMMITTED, ExecutionState.COMPENSATED):
                    logger.info(
                        f"Idempotency hit for key '{context.idempotency_key}': "
                        "returning cached result."
                    )
                    return cached_res

            # Idempotency concurrent execution protection
            if context.idempotency_key in self._active_idempotency:
                active_id = self._active_idempotency[context.idempotency_key]
                if active_id != context.execution_id:
                    logger.warning(
                        f"Concurrent idempotency execution attempt for key "
                        f"'{context.idempotency_key}'."
                    )

            self._active_executions[context.execution_id] = context
            self._active_idempotency[context.idempotency_key] = context.execution_id
            self._total_executions += 1

            if self.event_bus:
                try:
                    self.event_bus.publish(
                        RuntimeExecutionStarted(
                            execution_id=context.execution_id,
                            goal_id=context.goal_id,
                            schedule_id=context.schedule_id,
                            idempotency_key=context.idempotency_key,
                            attempt_number=context.attempt_number,
                        )
                    )
                except Exception as exc:
                    logger.warning(f"Failed to publish RuntimeExecutionStarted: {exc}")

        # Resolve configuration & RetryPolicy
        max_attempts = 3
        timeout_seconds = 30.0
        compensation_enabled = True

        if self.config is not None:
            max_attempts = self.config.get_typed("autonomy.execution_max_attempts", int, 3)
            timeout_seconds = self.config.get_typed(
                "autonomy.execution_timeout_seconds", float, 30.0
            )
            compensation_enabled = self.config.get_typed(
                "autonomy.execution_compensation_enabled", bool, True
            )

        if retry_policy is not None:
            max_attempts = retry_policy.max_attempts

        attempt = 1
        last_error: Exception | None = None
        failure_type: ExecutionFailureType | None = None
        output: Any | None = None
        rollback_performed = False
        compensation_performed = False
        final_state = ExecutionState.FAILED

        transaction = ExecutionTransaction()

        exec_start_dt = _parse_iso(now_iso)

        while attempt <= max_attempts:
            # Check Timeout / Deadline
            now_dt = _parse_iso(self.clock.now_iso())
            elapsed = (now_dt - exec_start_dt).total_seconds()

            if elapsed > timeout_seconds or (
                context.deadline_at and now_dt > _parse_iso(context.deadline_at)
            ):
                last_error = TimeoutError(f"Execution timed out after {elapsed:.1f}s")
                failure_type = ExecutionFailureType.TIMEOUT
                final_state = ExecutionState.TIMED_OUT
                if self.event_bus:
                    try:
                        self.event_bus.publish(
                            RuntimeExecutionTimedOut(
                                execution_id=context.execution_id,
                                timeout_seconds=timeout_seconds,
                            )
                        )
                    except Exception as exc:
                        logger.warning(f"Failed to publish RuntimeExecutionTimedOut: {exc}")
                break

            try:
                # Step 1: Validate
                val_ok = action.validate(context)
                if not val_ok:
                    raise ValueError(  # noqa: TRY301
                        f"Pre-condition validation failed for action '{action.action_id}'"
                    )

                if self.event_bus and attempt == 1:
                    try:
                        self.event_bus.publish(
                            RuntimeExecutionValidated(
                                execution_id=context.execution_id,
                                goal_id=context.goal_id,
                            )
                        )
                    except Exception as exc:
                        logger.warning(f"Failed to publish RuntimeExecutionValidated: {exc}")

                # Step 2: Execute
                transaction.register_step(action, context)
                output = action.execute(context)

                # Check Post-Execution Timeout / Deadline
                post_dt = _parse_iso(self.clock.now_iso())
                if (post_dt - exec_start_dt).total_seconds() > timeout_seconds or (
                    context.deadline_at and post_dt > _parse_iso(context.deadline_at)
                ):
                    elapsed = (post_dt - exec_start_dt).total_seconds()
                    raise TimeoutError(f"Execution timed out after {elapsed:.1f}s")  # noqa: TRY301

                # Step 3: Commit
                final_state = ExecutionState.COMMITTED
                last_error = None
                failure_type = None
                break  # Successful execution!

            except Exception as exc:
                last_error = exc
                if isinstance(exc, (ValueError, TypeError)):
                    failure_type = ExecutionFailureType.VALIDATION
                elif isinstance(exc, TimeoutError):
                    failure_type = ExecutionFailureType.TIMEOUT
                else:
                    failure_type = ExecutionFailureType.TRANSIENT

                if attempt < max_attempts and failure_type in (
                    retry_policy.retryable_failures
                    if retry_policy
                    else (ExecutionFailureType.TRANSIENT, ExecutionFailureType.TIMEOUT)
                ):
                    with self._lock:
                        self._retry_count += 1
                    if self.event_bus:
                        try:
                            self.event_bus.publish(
                                RuntimeExecutionRetrying(
                                    execution_id=context.execution_id,
                                    attempt_number=attempt,
                                    max_attempts=max_attempts,
                                    error=str(exc),
                                )
                            )
                        except Exception as p_exc:
                            logger.warning(f"Failed to publish RuntimeExecutionRetrying: {p_exc}")
                    attempt += 1
                    continue
                else:
                    final_state = ExecutionState.FAILED
                    break

        # Rollback / Compensation flow on failure
        if final_state in (ExecutionState.FAILED, ExecutionState.TIMED_OUT):
            rb_ok, rb_err = transaction.perform_rollback()
            if rb_ok:
                rollback_performed = True
                final_state = ExecutionState.ROLLED_BACK
                with self._lock:
                    self._rollback_count += 1
                if self.event_bus:
                    try:
                        self.event_bus.publish(
                            RuntimeExecutionRolledBack(
                                execution_id=context.execution_id,
                                reason=f"Rollback successful after failure: {last_error}",
                                success=True,
                            )
                        )
                    except Exception as exc:
                        logger.warning(f"Failed to publish RuntimeExecutionRolledBack: {exc}")
            elif compensation_enabled:
                if self.event_bus:
                    try:
                        self.event_bus.publish(
                            RuntimeExecutionCompensating(
                                execution_id=context.execution_id,
                                reason=f"Rollback failed ({rb_err}); initiating compensation.",
                            )
                        )
                    except Exception as exc:
                        logger.warning(f"Failed to publish RuntimeExecutionCompensating: {exc}")

                _comp_ok, _comp_err = transaction.perform_compensation()
                if _comp_ok:
                    compensation_performed = True
                    final_state = ExecutionState.COMPENSATED
                    with self._lock:
                        self._compensation_count += 1
                    if self.event_bus:
                        try:
                            self.event_bus.publish(
                                RuntimeExecutionCompensated(
                                    execution_id=context.execution_id,
                                    reason="Compensation completed successfully",
                                    success=True,
                                )
                            )
                        except Exception as exc:
                            logger.warning(f"Failed to publish RuntimeExecutionCompensated: {exc}")
                else:
                    final_state = ExecutionState.FAILED
                    failure_type = ExecutionFailureType.COMPENSATION_FAILURE

        # Build final ExecutionResult
        completed_at = self.clock.now_iso()
        success = final_state in (ExecutionState.COMMITTED, ExecutionState.COMPENSATED)

        res = ExecutionResult(
            execution_id=context.execution_id,
            goal_id=context.goal_id,
            schedule_id=context.schedule_id,
            idempotency_key=context.idempotency_key,
            success=success,
            state=final_state,
            attempt_number=attempt,
            started_at=context.started_at,
            completed_at=completed_at,
            error=str(last_error) if last_error else None,
            failure_type=failure_type,
            rollback_performed=rollback_performed,
            compensation_performed=compensation_performed,
            output=output,
        )

        with self._lock:
            # Clean up active state
            self._active_executions.pop(context.execution_id, None)
            if self._active_idempotency.get(context.idempotency_key) == context.execution_id:
                del self._active_idempotency[context.idempotency_key]

            # Cache in idempotency store & history
            self._idempotency_store[context.idempotency_key] = res
            self._execution_results[context.execution_id] = res

            history_limit = 100
            if self.config is not None:
                history_limit = self.config.get_typed("autonomy.execution_history_size", int, 100)
            self._execution_history.append(res)
            if len(self._execution_history) > history_limit:
                self._execution_history.pop(0)

            # Update counters
            if success:
                self._successful_executions += 1
            elif final_state == ExecutionState.CANCELLED:
                self._cancelled_executions += 1
            elif final_state == ExecutionState.TIMED_OUT:
                self._timed_out_executions += 1
            else:
                self._failed_executions += 1

            if self.event_bus:
                try:
                    if success:
                        self.event_bus.publish(
                            RuntimeExecutionCompleted(
                                execution_id=context.execution_id,
                                goal_id=context.goal_id,
                                state=final_state.value,
                            )
                        )
                    else:
                        self.event_bus.publish(
                            RuntimeExecutionFailed(
                                execution_id=context.execution_id,
                                goal_id=context.goal_id,
                                error=str(last_error) if last_error else "unknown_failure",
                                failure_type=failure_type.value if failure_type else "UNKNOWN",
                            )
                        )
                except Exception as exc:
                    logger.warning(f"Failed to publish execution outcome events: {exc}")

        return res

    def cancel_execution(self, execution_id: str, reason: str = "user_cancel") -> bool:
        """Cancels an active execution cooperative request."""
        with self._lock:
            ctx = self._active_executions.get(execution_id)
            if ctx is None:
                return False

            now_iso = self.clock.now_iso()
            res = ExecutionResult(
                execution_id=ctx.execution_id,
                goal_id=ctx.goal_id,
                schedule_id=ctx.schedule_id,
                idempotency_key=ctx.idempotency_key,
                success=False,
                state=ExecutionState.CANCELLED,
                attempt_number=ctx.attempt_number,
                started_at=ctx.started_at,
                completed_at=now_iso,
                error=f"Execution cancelled: {reason}",
                failure_type=ExecutionFailureType.CANCELLED,
                rollback_performed=False,
                compensation_performed=False,
            )
            self._active_executions.pop(execution_id, None)
            if self._active_idempotency.get(ctx.idempotency_key) == execution_id:
                del self._active_idempotency[ctx.idempotency_key]

            self._idempotency_store[ctx.idempotency_key] = res
            self._execution_results[execution_id] = res
            self._cancelled_executions += 1

            if self.event_bus:
                try:
                    self.event_bus.publish(
                        RuntimeExecutionCancelled(
                            execution_id=execution_id,
                            reason=reason,
                        )
                    )
                except Exception as exc:
                    logger.warning(f"Failed to publish RuntimeExecutionCancelled: {exc}")
            return True

    def get_execution_result(self, execution_id: str) -> ExecutionResult | None:
        with self._lock:
            return self._execution_results.get(execution_id)

    def get_idempotency_result(self, idempotency_key: str) -> ExecutionResult | None:
        with self._lock:
            return self._idempotency_store.get(idempotency_key)

    def get_active_executions(self) -> list[ExecutionContext]:
        with self._lock:
            return list(self._active_executions.values())

    def get_execution_history(self, limit: int = 100) -> list[ExecutionResult]:
        with self._lock:
            if limit <= 0:
                return []
            return list(self._execution_history[-limit:])

    def get_execution_snapshot(self) -> ExecutionStatusSnapshot:
        with self._lock:
            enabled = True
            if self.config is not None:
                enabled = self.config.get_typed("autonomy.execution_enabled", bool, True)

            return ExecutionStatusSnapshot(
                execution_enabled=enabled,
                total_executions=self._total_executions,
                successful_executions=self._successful_executions,
                failed_executions=self._failed_executions,
                cancelled_executions=self._cancelled_executions,
                timed_out_executions=self._timed_out_executions,
                retry_count=self._retry_count,
                rollback_count=self._rollback_count,
                compensation_count=self._compensation_count,
                active_executions_count=len(self._active_executions),
            )
