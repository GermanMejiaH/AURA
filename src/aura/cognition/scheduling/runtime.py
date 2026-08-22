from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from aura.events.bus import EventBus
from aura.events.models import (
    RuntimeDiagnosticSnapshotUpdated,
    RuntimeRecovered,
    RuntimeRecoveryAttempted,
    RuntimeRecoveryFailed,
    RuntimeStarted,
    RuntimeStopped,
    RuntimeTickCompleted,
    RuntimeTickFailed,
    RuntimeWorkerLost,
    RuntimeWorkerRecovered,
)
from aura.logging import get_logger

from .clock import Clock, SystemClock
from .dispatcher import DispatchResult, ScheduleDispatcher
from .policy import PolicyAdaptationEngine, SystemSignals

logger = get_logger("ContinuousAutonomyRuntime")


@dataclass(frozen=True)
class RuntimeMetricsSnapshot:
    """Immutable snapshot of ContinuousAutonomyRuntime execution metrics."""

    runtime_name: str
    is_running: bool
    worker_thread_alive: bool
    tick_count: int
    successful_ticks: int
    failed_ticks: int
    skipped_overlapping_ticks: int
    last_tick_at: str | None
    last_successful_tick_at: str | None
    last_failed_tick_at: str | None
    last_error: str | None
    started_at: str | None
    uptime_seconds: float


@dataclass(frozen=True)
class DiagnosticRecord:
    """Small immutable in-memory diagnostic log entry."""

    timestamp: str
    category: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeDiagnosticsSnapshot:
    """Immutable, thread-safe diagnostic snapshot of ContinuousAutonomyRuntime state."""

    runtime_name: str
    is_running: bool
    worker_thread_alive: bool
    thread_name: str | None
    tick_count: int
    successful_ticks: int
    failed_ticks: int
    skipped_overlapping_ticks: int
    started_at: str | None
    last_tick_at: str | None
    last_successful_tick_at: str | None
    last_failed_tick_at: str | None
    uptime_seconds: float
    last_error: str | None
    health_status: str
    recovery_attempts: int
    recovery_failures: int
    last_recovery_at: str | None
    last_state_change_at: str | None
    last_state_change_reason: str | None
    successful_recoveries: int = 0
    thread_alive: bool = True
    current_health_status: str = "HEALTHY"
    current_degradation_reason: str | None = None


@dataclass(frozen=True)
class RuntimeTelemetrySnapshot:
    """Immutable operational telemetry snapshot summarizing runtime health, ticks and recoveries."""

    runtime_name: str
    is_running: bool
    thread_alive: bool
    tick_count: int
    successful_ticks: int
    failed_ticks: int
    skipped_overlapping_ticks: int
    last_tick_at: str | None
    last_successful_tick_at: str | None
    last_failed_tick_at: str | None
    last_error: str | None
    started_at: str | None
    uptime_seconds: float
    recovery_attempts: int
    successful_recoveries: int
    failed_recoveries: int
    last_recovery_at: str | None
    current_health_status: str
    current_degradation_reason: str | None


@dataclass
class ContinuousAutonomyRuntime:
    """Thread-based runtime providing periodic scheduling ticks over ScheduleDispatcher."""

    dispatcher: ScheduleDispatcher
    clock: Clock = field(default_factory=SystemClock)
    event_bus: EventBus | None = None
    tick_interval_seconds: float = 1.0
    runtime_name: str = "AuraAutonomyRuntime"
    diagnostics_history_size: int = 50
    policy_engine: PolicyAdaptationEngine | None = None

    _running: bool = field(default=False, init=False)
    _tick_count: int = field(default=0, init=False)
    _successful_ticks: int = field(default=0, init=False)
    _failed_ticks: int = field(default=0, init=False)
    _skipped_overlapping_ticks: int = field(default=0, init=False)
    _last_tick_at: str | None = field(default=None, init=False)
    _last_successful_tick_at: str | None = field(default=None, init=False)
    _last_failed_tick_at: str | None = field(default=None, init=False)
    _last_error: str | None = field(default=None, init=False)
    _started_at: str | None = field(default=None, init=False)
    _started_at_dt: datetime | None = field(default=None, init=False)

    _recovery_failures_count: int = field(default=0, init=False)
    _last_recovery_at: str | None = field(default=None, init=False)
    _last_state_change_at: str | None = field(default=None, init=False)
    _last_state_change_reason: str | None = field(default=None, init=False)
    _diagnostics_history: list[DiagnosticRecord] = field(default_factory=list, init=False)

    _thread: threading.Thread | None = field(default=None, init=False)
    _stop_event: threading.Event = field(default_factory=threading.Event, init=False)
    _tick_lock: threading.RLock = field(default_factory=threading.RLock, init=False)
    _lifecycle_lock: threading.RLock = field(default_factory=threading.RLock, init=False)
    _recovery_attempts: list[datetime] = field(default_factory=list, init=False)

    @property
    def is_running(self) -> bool:
        with self._lifecycle_lock:
            return self._running

    @property
    def effective_tick_interval_seconds(self) -> float:
        """Returns the dynamic effective tick interval computed by PolicyAdaptationEngine if set."""
        with self._lifecycle_lock:
            configured = self.tick_interval_seconds
            if self.policy_engine is None:
                return configured
            snap = self.get_diagnostics_snapshot()
            signals = SystemSignals(
                health_status=snap.health_status,
                worker_thread_alive=snap.worker_thread_alive,
                failed_ticks=snap.failed_ticks,
                successful_ticks=snap.successful_ticks,
                skipped_overlapping_ticks=snap.skipped_overlapping_ticks,
                recovery_attempts=snap.recovery_attempts,
                recovery_failures=snap.recovery_failures,
                uptime_seconds=snap.uptime_seconds,
            )
            decision = self.policy_engine.evaluate_policy(
                signals=signals,
                configured_interval=configured,
                runtime_name=self.runtime_name,
            )
            return decision.effective_tick_interval_seconds

    @property
    def tick_count(self) -> int:
        return self._tick_count

    @property
    def last_tick_at(self) -> str | None:
        return self._last_tick_at

    def _record_diagnostic_entry(
        self,
        category: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Records a small diagnostic entry in bounded in-memory history (under _lifecycle_lock)."""
        now_iso = self.clock.now_iso()
        entry = DiagnosticRecord(
            timestamp=now_iso,
            category=category,
            message=message,
            details=details or {},
        )
        self._diagnostics_history.append(entry)
        max_size = max(1, self.diagnostics_history_size)
        if len(self._diagnostics_history) > max_size:
            self._diagnostics_history.pop(0)

    def get_diagnostics_history(self, limit: int = 50) -> list[DiagnosticRecord]:
        """Returns a thread-safe copy of recent diagnostic history entries."""
        with self._lifecycle_lock:
            safe_limit = max(1, limit)
            return list(self._diagnostics_history[-safe_limit:])

    def start(self) -> None:
        """Starts the periodic background runtime loop cleanly and idempotently."""
        with self._lifecycle_lock:
            if self._running and self._thread is not None and self._thread.is_alive():
                logger.debug(f"Runtime '{self.runtime_name}' is already running.")
                return

            now_iso = self.clock.now_iso()
            self._running = True
            self._started_at = now_iso
            self._started_at_dt = self.clock.now()
            self._last_state_change_at = now_iso
            self._last_state_change_reason = "start"
            self._record_diagnostic_entry("LIFECYCLE", "Runtime started")
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._worker_loop,
                name=self.runtime_name,
                daemon=True,
            )
            self._thread.start()

            logger.info(
                f"ContinuousAutonomyRuntime '{self.runtime_name}' started "
                f"(interval={self.tick_interval_seconds}s)"
            )

            if self.event_bus:
                self.event_bus.publish(
                    RuntimeStarted(
                        runtime_name=self.runtime_name,
                        tick_interval=self.tick_interval_seconds,
                        started_at=now_iso,
                    )
                )
                self.event_bus.publish(
                    RuntimeDiagnosticSnapshotUpdated(
                        runtime_name=self.runtime_name,
                        health_status="HEALTHY",
                    )
                )

    def stop(self, timeout: float = 5.0) -> None:
        """Stops the background runtime loop cleanly and idempotently."""
        with self._lifecycle_lock:
            if not self._running:
                logger.debug(f"Runtime '{self.runtime_name}' is already stopped.")
                return

            now_iso = self.clock.now_iso()
            self._running = False
            self._stop_event.set()
            self._last_state_change_at = now_iso
            self._last_state_change_reason = "stop"
            self._record_diagnostic_entry("LIFECYCLE", "Runtime stopped")

            if self._thread is not None and self._thread.is_alive():
                self._thread.join(timeout=timeout)
                self._thread = None

            logger.info(f"ContinuousAutonomyRuntime '{self.runtime_name}' stopped.")

            if self.event_bus:
                self.event_bus.publish(
                    RuntimeStopped(
                        runtime_name=self.runtime_name,
                        tick_count=self._tick_count,
                        stopped_at=now_iso,
                    )
                )
                self.event_bus.publish(
                    RuntimeDiagnosticSnapshotUpdated(
                        runtime_name=self.runtime_name,
                        health_status="STOPPED",
                    )
                )

    def tick(self, at_timestamp: str | None = None) -> list[DispatchResult]:
        """Executes a single synchronous tick evaluating due schedules via ScheduleDispatcher."""
        if not self._tick_lock.acquire(blocking=False):
            logger.warning(
                f"Previous tick in runtime '{self.runtime_name}' still in progress. "
                f"Skipping overlapping tick."
            )
            with self._lifecycle_lock:
                self._skipped_overlapping_ticks += 1
                self._record_diagnostic_entry("TICK", "Skipped overlapping tick")
            return []

        try:
            now_iso = at_timestamp or self.clock.now_iso()
            self._tick_count += 1
            self._last_tick_at = now_iso

            from ...telemetry import TelemetryManager

            TelemetryManager.get_instance().increment("autonomy_cycles")

            results = self.dispatcher.process_due_schedules(
                at_timestamp=now_iso,
                execute_goals=True,
            )
        except Exception as exc:
            now_iso = at_timestamp or self.clock.now_iso()
            logger.exception(
                f"Error during tick #{self._tick_count} in '{self.runtime_name}': {exc}"
            )
            with self._lifecycle_lock:
                self._failed_ticks += 1
                self._last_failed_tick_at = now_iso
                self._last_error = str(exc)
                self._record_diagnostic_entry("TICK_ERROR", f"Tick failed: {exc}")

            if self.event_bus:
                self.event_bus.publish(
                    RuntimeTickFailed(
                        tick_index=self._tick_count,
                        tick_timestamp=now_iso,
                        error=str(exc),
                    )
                )
            return []
        else:
            dispatched_count = sum(1 for r in results if r.dispatched)
            with self._lifecycle_lock:
                self._successful_ticks += 1
                self._last_successful_tick_at = now_iso

            if self.event_bus:
                self.event_bus.publish(
                    RuntimeTickCompleted(
                        tick_index=self._tick_count,
                        tick_timestamp=now_iso,
                        dispatched_count=dispatched_count,
                    )
                )

            return results
        finally:
            self._tick_lock.release()

    def get_metrics_snapshot(self) -> RuntimeMetricsSnapshot:
        """Returns an immutable snapshot of current runtime metrics."""
        with self._lifecycle_lock:
            thread_alive = self._thread is not None and self._thread.is_alive()
            uptime = 0.0
            if self._running and self._started_at_dt is not None:
                current_dt = self.clock.now()
                uptime = max(0.0, (current_dt - self._started_at_dt).total_seconds())

            return RuntimeMetricsSnapshot(
                runtime_name=self.runtime_name,
                is_running=self._running,
                worker_thread_alive=thread_alive,
                tick_count=self._tick_count,
                successful_ticks=self._successful_ticks,
                failed_ticks=self._failed_ticks,
                skipped_overlapping_ticks=self._skipped_overlapping_ticks,
                last_tick_at=self._last_tick_at,
                last_successful_tick_at=self._last_successful_tick_at,
                last_failed_tick_at=self._last_failed_tick_at,
                last_error=self._last_error,
                started_at=self._started_at,
                uptime_seconds=uptime,
            )

    def get_diagnostics_snapshot(self) -> RuntimeDiagnosticsSnapshot:
        """Returns a complete, thread-safe immutable diagnostic snapshot of runtime state."""
        with self._lifecycle_lock:
            thread_alive = self._thread is not None and self._thread.is_alive()
            thread_name = self._thread.name if self._thread is not None else None
            uptime = 0.0
            if self._running and self._started_at_dt is not None:
                current_dt = self.clock.now()
                uptime = max(0.0, (current_dt - self._started_at_dt).total_seconds())

            health_status = "HEALTHY"
            if not self._running:
                health_status = "STOPPED"
            elif not thread_alive:
                health_status = "DEGRADED"

            total_attempts = len(self._recovery_attempts)
            succ_recoveries = max(0, total_attempts - self._recovery_failures_count)
            return RuntimeDiagnosticsSnapshot(
                runtime_name=self.runtime_name,
                is_running=self._running,
                worker_thread_alive=thread_alive,
                thread_name=thread_name,
                tick_count=self._tick_count,
                successful_ticks=self._successful_ticks,
                failed_ticks=self._failed_ticks,
                skipped_overlapping_ticks=self._skipped_overlapping_ticks,
                started_at=self._started_at,
                last_tick_at=self._last_tick_at,
                last_successful_tick_at=self._last_successful_tick_at,
                last_failed_tick_at=self._last_failed_tick_at,
                uptime_seconds=uptime,
                last_error=self._last_error,
                health_status=health_status,
                recovery_attempts=total_attempts,
                recovery_failures=self._recovery_failures_count,
                last_recovery_at=self._last_recovery_at,
                last_state_change_at=self._last_state_change_at,
                last_state_change_reason=self._last_state_change_reason,
                successful_recoveries=succ_recoveries,
                thread_alive=thread_alive,
                current_health_status=health_status,
                current_degradation_reason=self._last_state_change_reason,
            )

    def get_telemetry_snapshot(self) -> RuntimeTelemetrySnapshot:
        """Returns an immutable operational telemetry snapshot summarizing runtime state."""
        with self._lifecycle_lock:
            snap = self.get_diagnostics_snapshot()
            return RuntimeTelemetrySnapshot(
                runtime_name=snap.runtime_name,
                is_running=snap.is_running,
                thread_alive=snap.worker_thread_alive,
                tick_count=snap.tick_count,
                successful_ticks=snap.successful_ticks,
                failed_ticks=snap.failed_ticks,
                skipped_overlapping_ticks=snap.skipped_overlapping_ticks,
                last_tick_at=snap.last_tick_at,
                last_successful_tick_at=snap.last_successful_tick_at,
                last_failed_tick_at=snap.last_failed_tick_at,
                last_error=snap.last_error,
                started_at=snap.started_at,
                uptime_seconds=snap.uptime_seconds,
                recovery_attempts=snap.recovery_attempts,
                successful_recoveries=snap.successful_recoveries,
                failed_recoveries=snap.recovery_failures,
                last_recovery_at=snap.last_recovery_at,
                current_health_status=snap.health_status,
                current_degradation_reason=snap.last_state_change_reason,
            )

    def get_diagnostics(self) -> RuntimeDiagnostics:
        """Returns a read-only RuntimeDiagnostics query helper for this runtime."""
        return RuntimeDiagnostics(runtime=self)

    def recover(
        self,
        reason: str = "health_check_failed",
        max_attempts: int = 3,
        backoff_seconds: float = 30.0,
    ) -> bool:
        """Executes controlled self-recovery of the worker thread with anti-storm backoff."""
        with self._lifecycle_lock:
            if not self._running:
                logger.warning(
                    f"Cannot recover runtime '{self.runtime_name}' because it is legally stopped."
                )
                return False

            if self._thread is not None and self._thread.is_alive():
                logger.debug(
                    f"Worker thread for '{self.runtime_name}' is already alive. "
                    f"Recovery condition already satisfied."
                )
                return True

            now_dt = self.clock.now()
            now_iso = self.clock.now_iso()
            cutoff = now_dt - timedelta(seconds=backoff_seconds)
            recent_attempts = [t for t in self._recovery_attempts if t >= cutoff]
            self._recovery_attempts = recent_attempts

            attempt_num = len(recent_attempts) + 1

            if attempt_num > max_attempts:
                self._recovery_failures_count += 1
                self._last_state_change_at = now_iso
                self._last_state_change_reason = f"recovery_failed:{reason}"
                self._record_diagnostic_entry(
                    "RECOVERY_FAILURE", f"Recovery storm limit reached for {reason}"
                )
                logger.warning(
                    f"Recovery storm prevented for '{self.runtime_name}': "
                    f"{len(recent_attempts)} attempts reached max ({max_attempts}) "
                    f"in {backoff_seconds}s window."
                )
                if self.event_bus:
                    self.event_bus.publish(
                        RuntimeRecoveryFailed(
                            runtime_name=self.runtime_name,
                            attempt_number=attempt_num,
                            reason=f"max_attempts_exceeded:{reason}",
                        )
                    )
                return False

            self._recovery_attempts.append(now_dt)
            self._last_recovery_at = now_iso
            self._last_state_change_at = now_iso
            self._last_state_change_reason = f"recovering:{reason}"
            self._record_diagnostic_entry("RECOVERY_ATTEMPT", f"Attempting recovery #{attempt_num}")

            if self.event_bus:
                self.event_bus.publish(
                    RuntimeWorkerLost(
                        runtime_name=self.runtime_name,
                        reason=reason,
                    )
                )
                self.event_bus.publish(
                    RuntimeRecoveryAttempted(
                        runtime_name=self.runtime_name,
                        attempt_number=attempt_num,
                        reason=reason,
                    )
                )

            # Stop existing thread cleanly if needed
            self._running = False
            self._stop_event.set()
            if self._thread is not None and self._thread.is_alive():
                self._thread.join(timeout=2.0)
            self._thread = None

            # Re-start worker thread cleanly
            self._running = True
            self._started_at = now_iso
            self._started_at_dt = now_dt
            self._last_state_change_at = now_iso
            self._last_state_change_reason = "recovered"
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._worker_loop,
                name=self.runtime_name,
                daemon=True,
            )
            self._thread.start()

            logger.info(f"Self-recovery #{attempt_num} completed for '{self.runtime_name}'")

            if self.event_bus:
                self.event_bus.publish(
                    RuntimeRecovered(
                        runtime_name=self.runtime_name,
                        attempt_number=attempt_num,
                        recovered_at=now_iso,
                    )
                )
                self.event_bus.publish(
                    RuntimeWorkerRecovered(
                        runtime_name=self.runtime_name,
                        attempt_number=attempt_num,
                        recovered_at=now_iso,
                    )
                )

            return True

    def _worker_loop(self) -> None:
        """Internal background thread worker loop."""
        while self._running:
            try:
                interval = self.effective_tick_interval_seconds
                if self._stop_event.wait(interval):
                    break
                if not self._running:
                    break
                self.tick()
            except Exception as exc:
                logger.exception(
                    f"Unhandled exception in runtime loop '{self.runtime_name}': {exc}"
                )


@dataclass(frozen=True)
class RuntimeDiagnostics:
    """Read-only operational diagnostics helper providing immutable snapshot queries."""

    runtime: ContinuousAutonomyRuntime

    def get_telemetry(self) -> RuntimeTelemetrySnapshot:
        return self.runtime.get_telemetry_snapshot()

    def get_snapshot(self) -> RuntimeDiagnosticsSnapshot:
        return self.runtime.get_diagnostics_snapshot()

    def get_history(self, limit: int = 50) -> list[DiagnosticRecord]:
        return self.runtime.get_diagnostics_history(limit=limit)
