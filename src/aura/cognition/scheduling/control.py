from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from aura.config import ConfigurationManager
from aura.events import (
    EventBus,
    RuntimeControlCommandCompleted,
    RuntimeControlCommandFailed,
    RuntimeControlCommandIssued,
    RuntimeStateChanged,
)
from aura.logging import get_logger

from .adaptation import (
    AdaptationProposal,
    AdaptationStatus,
    AdaptationStatusSnapshot,
    RuntimeAdaptivePolicyEngine,
)
from .assurance import (
    AssuranceSeverity,
    AuditRecord,
    InvariantViolation,
    RecoveryResult,
    RuntimeAssuranceEngine,
    RuntimeCheckpoint,
    RuntimeHealthSnapshot,
)
from .clock import Clock, SystemClock
from .runtime import (
    ContinuousAutonomyRuntime,
    DiagnosticRecord,
    RuntimeDiagnosticsSnapshot,
    RuntimeTelemetrySnapshot,
)

if TYPE_CHECKING:
    from .execution import (
        ExecutionContext,
        ExecutionResult,
        ExecutionStatusSnapshot,
        RuntimeExecutionEngine,
    )
    from .experience import (
        ActionExperience,
        ExperienceRecommendation,
        ExperienceStatusSnapshot,
        OutcomeRecord,
        RuntimeExperienceEngine,
    )
    from .governance import AutonomyScope, GovernanceStatusSnapshot, RuntimeGovernanceEngine
    from .orchestration import RuntimeOperation, RuntimeOrchestrator
    from .resolution import PolicyStatusSnapshot, RuntimePolicyEngine

logger = get_logger("RuntimeControlPlane")


class RuntimeOperationalState(str, Enum):
    """Operational state of ContinuousAutonomyRuntime derived deterministically."""

    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    RECOVERING = "RECOVERING"
    FAILED = "FAILED"


@dataclass(frozen=True)
class ControlCommand:
    """Immutable control command issued to RuntimeControlPlane."""

    command_id: str
    target_component: str
    action: str
    parameters: dict[str, Any]
    issued_at: str
    issuer: str = "operator"


@dataclass(frozen=True)
class ControlCommandResult:
    """Immutable result of a Control Plane operational command execution."""

    command: str
    success: bool
    previous_state: str
    resulting_state: str
    timestamp: str
    message: str


@dataclass(frozen=True)
class ControlAuditEntry:
    """Immutable audit record entry for operational control commands."""

    timestamp: str
    command: str
    success: bool
    previous_state: str
    resulting_state: str
    message: str


class RuntimeControlPlane:
    """Thread-safe Runtime Control Plane for operational management and control."""

    def __init__(
        self,
        runtime: ContinuousAutonomyRuntime,
        clock: Clock | None = None,
        event_bus: EventBus | None = None,
        config: ConfigurationManager | None = None,
        governance_engine: RuntimeGovernanceEngine | None = None,
        policy_engine: RuntimePolicyEngine | None = None,
        execution_engine: RuntimeExecutionEngine | None = None,
        experience_engine: RuntimeExperienceEngine | None = None,
        adaptation_engine: RuntimeAdaptivePolicyEngine | None = None,
        assurance_engine: RuntimeAssuranceEngine | None = None,
        orchestrator: RuntimeOrchestrator | None = None,
    ) -> None:
        self.runtime = runtime
        self.clock = clock or SystemClock()
        self.event_bus = event_bus
        self.config = config
        self.governance_engine = governance_engine
        self.policy_engine = policy_engine
        self.execution_engine = execution_engine
        self.experience_engine = experience_engine
        self.adaptation_engine = adaptation_engine
        self.assurance_engine = assurance_engine
        self.orchestrator = orchestrator
        self._lock = threading.RLock()
        self._audit_history: list[ControlAuditEntry] = []

    def set_governance_scope(
        self, scope: AutonomyScope | str, reason: str = "control_plane_override"
    ) -> None:
        """Sets authority scope via governance engine if registered."""
        if self.governance_engine is not None:
            self.governance_engine.set_authority_scope(scope, reason=reason)

    def get_governance_snapshot(self) -> GovernanceStatusSnapshot | None:
        """Returns governance status snapshot if governance engine is registered."""
        if self.governance_engine is not None:
            return self.governance_engine.get_governance_snapshot()
        return None

    def get_policy_snapshot(self) -> PolicyStatusSnapshot | None:
        """Returns policy status snapshot if policy engine is registered."""
        if self.policy_engine is not None:
            return self.policy_engine.get_policy_snapshot()
        return None

    def get_execution_snapshot(self) -> ExecutionStatusSnapshot | None:
        """Returns execution status snapshot if execution engine is registered."""
        if self.execution_engine is not None:
            return self.execution_engine.get_execution_snapshot()
        return None

    def get_active_executions(self) -> list[ExecutionContext]:
        """Returns active execution contexts if execution engine is registered."""
        if self.execution_engine is not None:
            return self.execution_engine.get_active_executions()
        return []

    def get_execution_history(self, limit: int = 100) -> list[ExecutionResult]:
        """Returns execution history if execution engine is registered."""
        if self.execution_engine is not None:
            return self.execution_engine.get_execution_history(limit=limit)
        return []

    def cancel_execution(self, execution_id: str, reason: str = "control_plane_cancel") -> bool:
        """Cancels an active execution via execution engine if registered."""
        if self.execution_engine is not None:
            return self.execution_engine.cancel_execution(execution_id, reason=reason)
        return False

    def get_experience_snapshot(self) -> ExperienceStatusSnapshot | None:
        """Returns experience status snapshot if experience engine is registered."""
        if self.experience_engine is not None:
            return self.experience_engine.get_experience_snapshot()
        return None

    def get_action_experience(self, action_id: str) -> ActionExperience | None:
        """Returns action experience if experience engine is registered."""
        if self.experience_engine is not None:
            return self.experience_engine.get_action_experience(action_id)
        return None

    def get_recent_outcomes(
        self, action_id: str | None = None, limit: int = 100
    ) -> list[OutcomeRecord]:
        """Returns recent outcomes if experience engine is registered."""
        if self.experience_engine is not None:
            return self.experience_engine.get_recent_outcomes(action_id=action_id, limit=limit)
        return []

    def get_recommendations(self, action_id: str | None = None) -> list[ExperienceRecommendation]:
        """Returns recommendations if experience engine is registered."""
        if self.experience_engine is not None:
            return self.experience_engine.get_recommendations(action_id=action_id)
        return []

    def get_failure_patterns(self, action_id: str | None = None) -> list[dict[str, Any]]:
        """Returns detected failure patterns if experience engine is registered."""
        if self.experience_engine is not None:
            return self.experience_engine.get_failure_patterns(action_id=action_id)
        return []

    def get_adaptation_snapshot(self) -> AdaptationStatusSnapshot | None:
        """Returns diagnostic snapshot of adaptation engine if registered."""
        if self.adaptation_engine is not None:
            return self.adaptation_engine.get_adaptation_snapshot()
        return None

    def get_pending_adaptations(self, action_id: str | None = None) -> list[AdaptationProposal]:
        """Returns proposals pending operator approval."""
        if self.adaptation_engine is not None:
            return self.adaptation_engine.store.get_proposals(
                action_id=action_id, status=AdaptationStatus.PENDING_APPROVAL
            )
        return []

    def get_adaptation_proposal(self, proposal_id: str) -> AdaptationProposal | None:
        """Returns specific adaptation proposal by ID."""
        if self.adaptation_engine is not None:
            return self.adaptation_engine.store.get_proposal(proposal_id)
        return None

    def approve_adaptation(
        self, proposal_id: str, operator_id: str, reason: str
    ) -> AdaptationProposal:
        """Approves a pending adaptation proposal. DOES NOT APPLY automatically."""
        if self.adaptation_engine is None:
            raise RuntimeError("Adaptation Engine not registered in Control Plane.")
        return self.adaptation_engine.approve_proposal(proposal_id, operator_id, reason)

    def reject_adaptation(
        self, proposal_id: str, operator_id: str, reason: str
    ) -> AdaptationProposal:
        """Rejects a pending adaptation proposal."""
        if self.adaptation_engine is None:
            raise RuntimeError("Adaptation Engine not registered in Control Plane.")
        return self.adaptation_engine.reject_proposal(proposal_id, operator_id, reason)

    def apply_adaptation(self, proposal_id: str) -> AdaptationProposal:
        """Applies an approved adaptation proposal."""
        if self.adaptation_engine is None:
            raise RuntimeError("Adaptation Engine not registered in Control Plane.")
        return self.adaptation_engine.apply_adaptation(proposal_id)

    def rollback_adaptation(self, proposal_id: str) -> AdaptationProposal:
        """Rolls back an applied adaptation proposal."""
        if self.adaptation_engine is None:
            raise RuntimeError("Adaptation Engine not registered in Control Plane.")
        return self.adaptation_engine.rollback_adaptation(proposal_id)

    def get_adaptation_history(
        self, action_id: str | None = None, limit: int = 100
    ) -> list[AdaptationProposal]:
        """Returns history of adaptation proposals."""
        if self.adaptation_engine is not None:
            return self.adaptation_engine.store.get_proposals(action_id=action_id, limit=limit)
        return []

    def get_status(self) -> RuntimeOperationalState:
        """Derives current operational state deterministically from runtime diagnostics."""
        snap = self.runtime.get_diagnostics_snapshot()
        if not snap.is_running:
            if snap.health_status == "FAILED":
                return RuntimeOperationalState.FAILED
            return RuntimeOperationalState.STOPPED
        if not snap.worker_thread_alive:
            if snap.recovery_attempts > 0 and snap.recovery_failures < snap.recovery_attempts:
                return RuntimeOperationalState.RECOVERING
            return RuntimeOperationalState.DEGRADED
        if snap.health_status == "DEGRADED":
            return RuntimeOperationalState.DEGRADED
        return RuntimeOperationalState.RUNNING

    def _record_audit(self, entry: ControlAuditEntry) -> None:
        max_size = 100
        if self.config is not None:
            max_size = self.config.get_typed("autonomy.control_history_size", int, 100)
            if max_size <= 0:
                max_size = 100

        with self._lock:
            self._audit_history.append(entry)
            if len(self._audit_history) > max_size:
                self._audit_history.pop(0)

    def get_audit_history(self, limit: int = 100) -> list[Any]:
        with self._lock:
            if limit <= 0:
                return []
            if self.assurance_engine is not None:
                return self.assurance_engine.get_audit_history(limit=limit)
            return list(self._audit_history[-limit:])

    def _check_enabled(self) -> bool:
        if self.config is not None:
            return self.config.get_typed("autonomy.control_enabled", bool, True)
        return True

    def start(self) -> ControlCommandResult:
        """Starts the autonomy runtime cleanly and idempotently."""
        with self._lock:
            now_iso = self.clock.now_iso()
            prev_state = self.get_status()

            if not self._check_enabled():
                res = ControlCommandResult(
                    command="START",
                    success=False,
                    previous_state=prev_state.value,
                    resulting_state=prev_state.value,
                    timestamp=now_iso,
                    message="Control Plane is disabled by configuration",
                )
                self._record_audit(
                    ControlAuditEntry(
                        now_iso, "START", False, prev_state.value, prev_state.value, res.message
                    )
                )
                return res

            if self.event_bus:
                self.event_bus.publish(
                    RuntimeControlCommandIssued(command="START", command_timestamp=now_iso)
                )

            if prev_state in {RuntimeOperationalState.RUNNING, RuntimeOperationalState.STARTING}:
                res = ControlCommandResult(
                    command="START",
                    success=True,
                    previous_state=prev_state.value,
                    resulting_state=prev_state.value,
                    timestamp=now_iso,
                    message="Runtime already running",
                )
                self._record_audit(
                    ControlAuditEntry(
                        now_iso, "START", True, prev_state.value, prev_state.value, res.message
                    )
                )
                return res

            try:
                self.runtime.start()
                new_state = self.get_status()
                res = ControlCommandResult(
                    command="START",
                    success=True,
                    previous_state=prev_state.value,
                    resulting_state=new_state.value,
                    timestamp=now_iso,
                    message="Runtime started successfully",
                )
                if self.event_bus:
                    self.event_bus.publish(
                        RuntimeControlCommandCompleted(
                            command="START",
                            success=True,
                            previous_state=prev_state.value,
                            resulting_state=new_state.value,
                        )
                    )
                    if prev_state != new_state:
                        self.event_bus.publish(
                            RuntimeStateChanged(
                                previous_state=prev_state.value,
                                new_state=new_state.value,
                                reason="command_start",
                            )
                        )
            except Exception as exc:
                new_state = self.get_status()
                res = ControlCommandResult(
                    command="START",
                    success=False,
                    previous_state=prev_state.value,
                    resulting_state=new_state.value,
                    timestamp=now_iso,
                    message=f"Start failed: {exc}",
                )
                if self.event_bus:
                    self.event_bus.publish(
                        RuntimeControlCommandFailed(
                            command="START", error=str(exc), previous_state=prev_state.value
                        )
                    )

            self._record_audit(
                ControlAuditEntry(
                    now_iso,
                    "START",
                    res.success,
                    prev_state.value,
                    res.resulting_state,
                    res.message,
                )
            )
            return res

    def stop(self, timeout: float = 5.0) -> ControlCommandResult:
        """Stops the autonomy runtime cleanly and idempotently."""
        with self._lock:
            now_iso = self.clock.now_iso()
            prev_state = self.get_status()

            if not self._check_enabled():
                res = ControlCommandResult(
                    command="STOP",
                    success=False,
                    previous_state=prev_state.value,
                    resulting_state=prev_state.value,
                    timestamp=now_iso,
                    message="Control Plane is disabled by configuration",
                )
                self._record_audit(
                    ControlAuditEntry(
                        now_iso, "STOP", False, prev_state.value, prev_state.value, res.message
                    )
                )
                return res

            if self.event_bus:
                self.event_bus.publish(
                    RuntimeControlCommandIssued(command="STOP", command_timestamp=now_iso)
                )

            if prev_state == RuntimeOperationalState.STOPPED:
                res = ControlCommandResult(
                    command="STOP",
                    success=True,
                    previous_state=prev_state.value,
                    resulting_state=prev_state.value,
                    timestamp=now_iso,
                    message="Runtime already stopped",
                )
                self._record_audit(
                    ControlAuditEntry(
                        now_iso, "STOP", True, prev_state.value, prev_state.value, res.message
                    )
                )
                return res

            try:
                self.runtime.stop(timeout=timeout)
                new_state = self.get_status()
                res = ControlCommandResult(
                    command="STOP",
                    success=True,
                    previous_state=prev_state.value,
                    resulting_state=new_state.value,
                    timestamp=now_iso,
                    message="Runtime stopped successfully",
                )
                if self.event_bus:
                    self.event_bus.publish(
                        RuntimeControlCommandCompleted(
                            command="STOP",
                            success=True,
                            previous_state=prev_state.value,
                            resulting_state=new_state.value,
                        )
                    )
                    if prev_state != new_state:
                        self.event_bus.publish(
                            RuntimeStateChanged(
                                previous_state=prev_state.value,
                                new_state=new_state.value,
                                reason="command_stop",
                            )
                        )
            except Exception as exc:
                new_state = self.get_status()
                res = ControlCommandResult(
                    command="STOP",
                    success=False,
                    previous_state=prev_state.value,
                    resulting_state=new_state.value,
                    timestamp=now_iso,
                    message=f"Stop failed: {exc}",
                )
                if self.event_bus:
                    self.event_bus.publish(
                        RuntimeControlCommandFailed(
                            command="STOP", error=str(exc), previous_state=prev_state.value
                        )
                    )

            self._record_audit(
                ControlAuditEntry(
                    now_iso,
                    "STOP",
                    res.success,
                    prev_state.value,
                    res.resulting_state,
                    res.message,
                )
            )
            return res

    def restart(self, timeout: float = 5.0) -> ControlCommandResult:
        """Restarts the autonomy runtime safely via atomic stop + start."""
        with self._lock:
            now_iso = self.clock.now_iso()
            prev_state = self.get_status()

            if not self._check_enabled():
                res = ControlCommandResult(
                    command="RESTART",
                    success=False,
                    previous_state=prev_state.value,
                    resulting_state=prev_state.value,
                    timestamp=now_iso,
                    message="Control Plane is disabled by configuration",
                )
                self._record_audit(
                    ControlAuditEntry(
                        now_iso, "RESTART", False, prev_state.value, prev_state.value, res.message
                    )
                )
                return res

            if self.event_bus:
                self.event_bus.publish(
                    RuntimeControlCommandIssued(command="RESTART", command_timestamp=now_iso)
                )

            try:
                if prev_state != RuntimeOperationalState.STOPPED:
                    self.runtime.stop(timeout=timeout)
                self.runtime.start()
                new_state = self.get_status()
                res = ControlCommandResult(
                    command="RESTART",
                    success=True,
                    previous_state=prev_state.value,
                    resulting_state=new_state.value,
                    timestamp=now_iso,
                    message="Runtime restarted successfully",
                )
                if self.event_bus:
                    self.event_bus.publish(
                        RuntimeControlCommandCompleted(
                            command="RESTART",
                            success=True,
                            previous_state=prev_state.value,
                            resulting_state=new_state.value,
                        )
                    )
                    if prev_state != new_state:
                        self.event_bus.publish(
                            RuntimeStateChanged(
                                previous_state=prev_state.value,
                                new_state=new_state.value,
                                reason="command_restart",
                            )
                        )
            except Exception as exc:
                new_state = self.get_status()
                res = ControlCommandResult(
                    command="RESTART",
                    success=False,
                    previous_state=prev_state.value,
                    resulting_state=new_state.value,
                    timestamp=now_iso,
                    message=f"Restart failed: {exc}",
                )
                if self.event_bus:
                    self.event_bus.publish(
                        RuntimeControlCommandFailed(
                            command="RESTART", error=str(exc), previous_state=prev_state.value
                        )
                    )

            self._record_audit(
                ControlAuditEntry(
                    now_iso,
                    "RESTART",
                    res.success,
                    prev_state.value,
                    res.resulting_state,
                    res.message,
                )
            )
            return res

    def recover(
        self,
        reason: str = "manual_control_recovery",
        max_attempts: int = 3,
        backoff_seconds: float = 30.0,
    ) -> ControlCommandResult:
        """Executes controlled worker thread recovery cleanly and idempotently."""
        with self._lock:
            now_iso = self.clock.now_iso()
            prev_state = self.get_status()

            if not self._check_enabled():
                res = ControlCommandResult(
                    command="RECOVER",
                    success=False,
                    previous_state=prev_state.value,
                    resulting_state=prev_state.value,
                    timestamp=now_iso,
                    message="Control Plane is disabled by configuration",
                )
                self._record_audit(
                    ControlAuditEntry(
                        now_iso, "RECOVER", False, prev_state.value, prev_state.value, res.message
                    )
                )
                return res

            if self.event_bus:
                self.event_bus.publish(
                    RuntimeControlCommandIssued(command="RECOVER", command_timestamp=now_iso)
                )

            if prev_state == RuntimeOperationalState.RUNNING:
                res = ControlCommandResult(
                    command="RECOVER",
                    success=True,
                    previous_state=prev_state.value,
                    resulting_state=prev_state.value,
                    timestamp=now_iso,
                    message="Runtime already healthy and running",
                )
                self._record_audit(
                    ControlAuditEntry(
                        now_iso, "RECOVER", True, prev_state.value, prev_state.value, res.message
                    )
                )
                return res

            if prev_state == RuntimeOperationalState.STOPPED:
                res = ControlCommandResult(
                    command="RECOVER",
                    success=False,
                    previous_state=prev_state.value,
                    resulting_state=prev_state.value,
                    timestamp=now_iso,
                    message="Cannot recover legally stopped runtime",
                )
                self._record_audit(
                    ControlAuditEntry(
                        now_iso, "RECOVER", False, prev_state.value, prev_state.value, res.message
                    )
                )
                return res

            try:
                ok = self.runtime.recover(
                    reason=reason, max_attempts=max_attempts, backoff_seconds=backoff_seconds
                )
                new_state = self.get_status()
                msg = (
                    "Self-recovery executed successfully"
                    if ok
                    else "Self-recovery failed or budget exhausted"
                )
                res = ControlCommandResult(
                    command="RECOVER",
                    success=ok,
                    previous_state=prev_state.value,
                    resulting_state=new_state.value,
                    timestamp=now_iso,
                    message=msg,
                )
                if self.event_bus:
                    if ok:
                        self.event_bus.publish(
                            RuntimeControlCommandCompleted(
                                command="RECOVER",
                                success=True,
                                previous_state=prev_state.value,
                                resulting_state=new_state.value,
                            )
                        )
                        if prev_state != new_state:
                            self.event_bus.publish(
                                RuntimeStateChanged(
                                    previous_state=prev_state.value,
                                    new_state=new_state.value,
                                    reason="command_recover",
                                )
                            )
                    else:
                        self.event_bus.publish(
                            RuntimeControlCommandFailed(
                                command="RECOVER",
                                error=msg,
                                previous_state=prev_state.value,
                            )
                        )
            except Exception as exc:
                new_state = self.get_status()
                res = ControlCommandResult(
                    command="RECOVER",
                    success=False,
                    previous_state=prev_state.value,
                    resulting_state=new_state.value,
                    timestamp=now_iso,
                    message=f"Recover failed: {exc}",
                )
                if self.event_bus:
                    self.event_bus.publish(
                        RuntimeControlCommandFailed(
                            command="RECOVER", error=str(exc), previous_state=prev_state.value
                        )
                    )

            self._record_audit(
                ControlAuditEntry(
                    now_iso,
                    "RECOVER",
                    res.success,
                    prev_state.value,
                    res.resulting_state,
                    res.message,
                )
            )
            return res

    def get_telemetry(self) -> RuntimeTelemetrySnapshot:
        return self.runtime.get_telemetry_snapshot()

    def get_diagnostics(self) -> RuntimeDiagnosticsSnapshot:
        return self.runtime.get_diagnostics_snapshot()

    def get_history(self, limit: int = 50) -> list[DiagnosticRecord]:
        return self.runtime.get_diagnostics_history(limit=limit)

    def get_health_snapshot(self) -> RuntimeHealthSnapshot | None:
        """Returns the immutable RuntimeHealthSnapshot from assurance_engine if available."""
        if self.assurance_engine is None:
            return None
        return self.assurance_engine.get_health_snapshot()

    def get_invariant_violations(
        self, component: str | None = None, severity: AssuranceSeverity | None = None
    ) -> list[InvariantViolation]:
        """Returns recorded invariant violations from assurance_engine."""
        if self.assurance_engine is None:
            return []
        return self.assurance_engine.store.get_violations(component=component, severity=severity)

    def query_audit(
        self,
        correlation_id: str | None = None,
        stage: str | None = None,
        component: str | None = None,
        event_type: str | None = None,
        severity: AssuranceSeverity | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int = 100,
    ) -> list[AuditRecord]:
        """Queries audit records matching specified parameters."""
        if self.assurance_engine is None:
            return []
        return self.assurance_engine.query_audit(
            correlation_id=correlation_id,
            stage=stage,
            component=component,
            event_type=event_type,
            severity=severity,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )

    def create_checkpoint(
        self, reason: str = "control_plane_checkpoint"
    ) -> RuntimeCheckpoint | None:
        """Creates a operational checkpoint via assurance_engine."""
        if self.assurance_engine is None:
            return None
        return self.assurance_engine.create_checkpoint(reason=reason)

    def get_checkpoint(self, checkpoint_id: str) -> RuntimeCheckpoint | None:
        """Retrieves a checkpoint by ID."""
        if self.assurance_engine is None:
            return None
        return self.assurance_engine.get_checkpoint(checkpoint_id)

    def list_checkpoints(self, limit: int = 100) -> list[RuntimeCheckpoint]:
        """Lists available checkpoints."""
        if self.assurance_engine is None:
            return []
        return self.assurance_engine.list_checkpoints(limit=limit)

    def recover_assurance(self, reason: str = "control_plane_recovery") -> RecoveryResult | None:
        """Executes safe operational recovery via assurance_engine."""
        if self.assurance_engine is None:
            return None
        return self.assurance_engine.recover(reason=reason)

    def get_recovery_history(self, limit: int = 100) -> list[RecoveryResult]:
        """Returns history of operational recoveries."""
        if self.assurance_engine is None:
            return []
        return self.assurance_engine.store.get_recoveries(limit=limit)

    def enter_safe_mode(self, reason: str = "control_plane_safe_mode") -> None:
        """Transitions assurance engine into SAFE_MODE."""
        if self.assurance_engine is not None:
            self.assurance_engine.enter_safe_mode(reason=reason)

    def exit_safe_mode(self, force: bool = False) -> bool:
        """Attempts to exit SAFE_MODE after verification."""
        if self.assurance_engine is None:
            return True
        return self.assurance_engine.exit_safe_mode(force=force)

    def get_operation(self, operation_id: str) -> RuntimeOperation | None:
        """Retrieves operation by ID from orchestrator."""
        if self.orchestrator is None:
            return None
        return self.orchestrator.get_operation(operation_id)

    def get_operation_history(self, limit: int = 100) -> list[RuntimeOperation]:
        """Returns operation history from orchestrator."""
        if self.orchestrator is None:
            return []
        return self.orchestrator.get_operation_history(limit=limit)

    def get_active_operations(self) -> list[RuntimeOperation]:
        """Returns currently active operations from orchestrator."""
        if self.orchestrator is None:
            return []
        return self.orchestrator.list_active_operations()

    def cancel_operation(
        self, operation_id: str, reason: str = "manual_cancellation"
    ) -> RuntimeOperation | None:
        """Cancels an in-flight operation via orchestrator."""
        if self.orchestrator is None:
            return None
        return self.orchestrator.cancel_operation(operation_id, reason=reason)
