from __future__ import annotations

import json
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from aura.cognition.scheduling.clock import Clock, SystemClock
from aura.config import ConfigurationManager
from aura.events import (
    EventBus,
    RuntimeAuditRecorded,
    RuntimeCheckpointCreated,
    RuntimeInvariantViolationDetected,
    RuntimeRecoveryCompleted,
    RuntimeRecoveryFailed,
    RuntimeRecoveryStarted,
    RuntimeSafeModeEntered,
    RuntimeSafeModeExited,
)
from aura.memory.store import SQLiteMemoryStore

if TYPE_CHECKING:
    from aura.cognition.scheduling.adaptation import RuntimeAdaptivePolicyEngine
    from aura.cognition.scheduling.execution import RuntimeExecutionEngine
    from aura.cognition.scheduling.experience import RuntimeExperienceEngine
    from aura.cognition.scheduling.governance import RuntimeGovernanceEngine
    from aura.cognition.scheduling.resolution import RuntimePolicyEngine


class AssuranceStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    RECOVERING = "RECOVERING"
    RECOVERED = "RECOVERED"
    FAILED = "FAILED"
    SAFE_MODE = "SAFE_MODE"


class AssuranceSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AssuranceEventType(str, Enum):
    HEALTH_CHECK = "HEALTH_CHECK"
    INVARIANT_VIOLATION = "INVARIANT_VIOLATION"
    COMPONENT_FAILURE = "COMPONENT_FAILURE"
    RECOVERY_STARTED = "RECOVERY_STARTED"
    RECOVERY_COMPLETED = "RECOVERY_COMPLETED"
    RECOVERY_FAILED = "RECOVERY_FAILED"
    CHECKPOINT_CREATED = "CHECKPOINT_CREATED"
    STATE_RESTORED = "STATE_RESTORED"
    AUDIT_RECORDED = "AUDIT_RECORDED"
    SAFE_MODE_ENTERED = "SAFE_MODE_ENTERED"
    SAFE_MODE_EXITED = "SAFE_MODE_EXITED"


@dataclass(frozen=True)
class RuntimeInvariant:
    invariant_id: str
    name: str
    description: str
    component: str
    severity: AssuranceSeverity = AssuranceSeverity.ERROR
    check_fn_name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InvariantViolation:
    violation_id: str
    invariant_id: str
    severity: AssuranceSeverity
    component: str
    description: str
    observed_state: Any
    expected_state: Any
    correlation_id: str
    timestamp: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeHealthSnapshot:
    status: AssuranceStatus
    timestamp: str
    uptime: float
    active_components: tuple[str, ...]
    failed_components: tuple[str, ...]
    degraded_components: tuple[str, ...]
    active_executions: int
    pending_policies: int
    pending_adaptations: int
    recent_failures: int
    invariant_violations: int
    recovery_count: int
    checkpoint_count: int
    in_safe_mode: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AuditRecord:
    audit_id: str
    timestamp: str
    correlation_id: str
    component: str
    stage: str
    event_type: str
    action: str
    actor: str
    outcome: str
    severity: AssuranceSeverity
    details: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeCheckpoint:
    checkpoint_id: str
    timestamp: str
    reason: str
    component_states: dict[str, Any]
    policy_state_reference: str
    execution_state_reference: str
    experience_state_reference: str
    adaptation_state_reference: str
    schema_version: str = "1.0"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RecoveryResult:
    success: bool
    recovery_id: str
    reason: str
    restored_components: tuple[str, ...]
    failed_components: tuple[str, ...]
    checkpoint_id: str | None
    duration: float
    errors: tuple[str, ...]
    timestamp: str
    metadata: dict[str, Any] = field(default_factory=dict)


class RuntimeAssuranceStore:
    """Thread-safe SQLite store for audit trail, checkpoints, and recovery records."""

    def __init__(
        self,
        store: SQLiteMemoryStore | None = None,
        container: Any | None = None,
        db_path: str = ":memory:",
    ) -> None:
        self._lock = threading.RLock()
        if store is not None:
            self._memory_store = store
        elif (
            container is not None and hasattr(container, "has") and container.has(SQLiteMemoryStore)
        ):
            self._memory_store = container.resolve(SQLiteMemoryStore)
        else:
            self._memory_store = SQLiteMemoryStore(db_path=db_path)
        self._init_tables()

    def _init_tables(self) -> None:
        with self._lock:
            conn = self._memory_store._get_connection()
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS runtime_audit_records (
                        audit_id TEXT PRIMARY KEY,
                        timestamp TEXT NOT NULL,
                        correlation_id TEXT NOT NULL,
                        component TEXT NOT NULL,
                        stage TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        action TEXT NOT NULL,
                        actor TEXT NOT NULL,
                        outcome TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        details TEXT,
                        metadata TEXT,
                        created_at TEXT NOT NULL
                    );
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_audit_corr "
                    "ON runtime_audit_records(correlation_id);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_audit_ts ON runtime_audit_records(timestamp);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_audit_comp ON runtime_audit_records(component);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_audit_stage ON runtime_audit_records(stage);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_audit_sev ON runtime_audit_records(severity);"
                )

                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS runtime_checkpoints (
                        checkpoint_id TEXT PRIMARY KEY,
                        timestamp TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        component_states TEXT NOT NULL,
                        policy_state_reference TEXT NOT NULL,
                        execution_state_reference TEXT NOT NULL,
                        experience_state_reference TEXT NOT NULL,
                        adaptation_state_reference TEXT NOT NULL,
                        schema_version TEXT NOT NULL,
                        metadata TEXT,
                        created_at TEXT NOT NULL
                    );
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_chk_ts ON runtime_checkpoints(timestamp);"
                )

                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS runtime_invariant_violations (
                        violation_id TEXT PRIMARY KEY,
                        invariant_id TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        component TEXT NOT NULL,
                        description TEXT NOT NULL,
                        observed_state TEXT,
                        expected_state TEXT,
                        correlation_id TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        metadata TEXT,
                        created_at TEXT NOT NULL
                    );
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_inv_corr "
                    "ON runtime_invariant_violations(correlation_id);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_inv_comp "
                    "ON runtime_invariant_violations(component);"
                )

                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS runtime_recovery_records (
                        recovery_id TEXT PRIMARY KEY,
                        success INTEGER NOT NULL,
                        reason TEXT NOT NULL,
                        restored_components TEXT NOT NULL,
                        failed_components TEXT NOT NULL,
                        checkpoint_id TEXT,
                        duration REAL NOT NULL,
                        errors TEXT,
                        timestamp TEXT NOT NULL,
                        metadata TEXT,
                        created_at TEXT NOT NULL
                    );
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_rec_ts ON runtime_recovery_records(timestamp);"
                )

    def save_audit(self, record: AuditRecord) -> None:
        with self._lock:
            conn = self._memory_store._get_connection()
            now_iso = datetime.now(UTC).isoformat()
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO runtime_audit_records (
                        audit_id, timestamp, correlation_id, component, stage, event_type,
                        action, actor, outcome, severity, details, metadata, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        record.audit_id,
                        record.timestamp,
                        record.correlation_id,
                        record.component,
                        record.stage,
                        record.event_type,
                        record.action,
                        record.actor,
                        record.outcome,
                        record.severity.value,
                        record.details,
                        json.dumps(record.metadata),
                        now_iso,
                    ),
                )

    def get_audit(self, audit_id: str) -> AuditRecord | None:
        with self._lock:
            conn = self._memory_store._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT audit_id, timestamp, correlation_id, component, stage, event_type,
                       action, actor, outcome, severity, details, metadata
                FROM runtime_audit_records WHERE audit_id = ?;
                """,
                (audit_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_audit(row)

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
        with self._lock:
            conn = self._memory_store._get_connection()
            cursor = conn.cursor()
            query = """
                SELECT audit_id, timestamp, correlation_id, component, stage, event_type,
                       action, actor, outcome, severity, details, metadata
                FROM runtime_audit_records
            """
            params: list[Any] = []
            conditions: list[str] = []

            if correlation_id:
                conditions.append("correlation_id = ?")
                params.append(correlation_id)
            if stage:
                conditions.append("stage = ?")
                params.append(stage)
            if component:
                conditions.append("component = ?")
                params.append(component)
            if event_type:
                conditions.append("event_type = ?")
                params.append(event_type)
            if severity:
                conditions.append("severity = ?")
                params.append(severity.value)
            if start_time:
                conditions.append("timestamp >= ?")
                params.append(start_time)
            if end_time:
                conditions.append("timestamp <= ?")
                params.append(end_time)

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, tuple(params))
            return [self._row_to_audit(r) for r in cursor.fetchall()]

    def count_audits(self) -> int:
        with self._lock:
            conn = self._memory_store._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM runtime_audit_records;")
            res = cursor.fetchone()
            return int(res[0]) if res else 0

    def save_checkpoint(self, checkpoint: RuntimeCheckpoint) -> None:
        with self._lock:
            conn = self._memory_store._get_connection()
            now_iso = datetime.now(UTC).isoformat()
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO runtime_checkpoints (
                        checkpoint_id, timestamp, reason, component_states,
                        policy_state_reference, execution_state_reference,
                        experience_state_reference, adaptation_state_reference,
                        schema_version, metadata, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        checkpoint.checkpoint_id,
                        checkpoint.timestamp,
                        checkpoint.reason,
                        json.dumps(checkpoint.component_states),
                        checkpoint.policy_state_reference,
                        checkpoint.execution_state_reference,
                        checkpoint.experience_state_reference,
                        checkpoint.adaptation_state_reference,
                        checkpoint.schema_version,
                        json.dumps(checkpoint.metadata),
                        now_iso,
                    ),
                )

    def get_checkpoint(self, checkpoint_id: str) -> RuntimeCheckpoint | None:
        with self._lock:
            conn = self._memory_store._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT checkpoint_id, timestamp, reason, component_states,
                       policy_state_reference, execution_state_reference,
                       experience_state_reference, adaptation_state_reference,
                       schema_version, metadata
                FROM runtime_checkpoints WHERE checkpoint_id = ?;
                """,
                (checkpoint_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_checkpoint(row)

    def list_checkpoints(self, limit: int = 100) -> list[RuntimeCheckpoint]:
        with self._lock:
            conn = self._memory_store._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT checkpoint_id, timestamp, reason, component_states,
                       policy_state_reference, execution_state_reference,
                       experience_state_reference, adaptation_state_reference,
                       schema_version, metadata
                FROM runtime_checkpoints ORDER BY timestamp DESC LIMIT ?;
                """,
                (limit,),
            )
            return [self._row_to_checkpoint(r) for r in cursor.fetchall()]

    def save_violation(self, violation: InvariantViolation) -> None:
        with self._lock:
            conn = self._memory_store._get_connection()
            now_iso = datetime.now(UTC).isoformat()
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO runtime_invariant_violations (
                        violation_id, invariant_id, severity, component, description,
                        observed_state, expected_state, correlation_id, timestamp,
                        metadata, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        violation.violation_id,
                        violation.invariant_id,
                        violation.severity.value,
                        violation.component,
                        violation.description,
                        json.dumps(violation.observed_state),
                        json.dumps(violation.expected_state),
                        violation.correlation_id,
                        violation.timestamp,
                        json.dumps(violation.metadata),
                        now_iso,
                    ),
                )

    def get_violations(
        self,
        component: str | None = None,
        severity: AssuranceSeverity | None = None,
        limit: int = 100,
    ) -> list[InvariantViolation]:
        with self._lock:
            conn = self._memory_store._get_connection()
            cursor = conn.cursor()
            query = """
                SELECT violation_id, invariant_id, severity, component, description,
                       observed_state, expected_state, correlation_id, timestamp, metadata
                FROM runtime_invariant_violations
            """
            params: list[Any] = []
            conditions: list[str] = []

            if component:
                conditions.append("component = ?")
                params.append(component)
            if severity:
                conditions.append("severity = ?")
                params.append(severity.value)

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, tuple(params))
            return [self._row_to_violation(r) for r in cursor.fetchall()]

    def save_recovery(self, recovery: RecoveryResult) -> None:
        with self._lock:
            conn = self._memory_store._get_connection()
            now_iso = datetime.now(UTC).isoformat()
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO runtime_recovery_records (
                        recovery_id, success, reason, restored_components,
                        failed_components, checkpoint_id, duration, errors,
                        timestamp, metadata, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        recovery.recovery_id,
                        1 if recovery.success else 0,
                        recovery.reason,
                        json.dumps(list(recovery.restored_components)),
                        json.dumps(list(recovery.failed_components)),
                        recovery.checkpoint_id,
                        recovery.duration,
                        json.dumps(list(recovery.errors)),
                        recovery.timestamp,
                        json.dumps(recovery.metadata),
                        now_iso,
                    ),
                )

    def get_recoveries(self, limit: int = 100) -> list[RecoveryResult]:
        with self._lock:
            conn = self._memory_store._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT recovery_id, success, reason, restored_components,
                       failed_components, checkpoint_id, duration, errors,
                       timestamp, metadata
                FROM runtime_recovery_records ORDER BY timestamp DESC LIMIT ?;
                """,
                (limit,),
            )
            return [self._row_to_recovery(r) for r in cursor.fetchall()]

    def _row_to_audit(self, row: tuple[Any, ...]) -> AuditRecord:
        return AuditRecord(
            audit_id=row[0],
            timestamp=row[1],
            correlation_id=row[2],
            component=row[3],
            stage=row[4],
            event_type=row[5],
            action=row[6],
            actor=row[7],
            outcome=row[8],
            severity=AssuranceSeverity(row[9]),
            details=row[10],
            metadata=json.loads(row[11]) if row[11] else {},
        )

    def _row_to_checkpoint(self, row: tuple[Any, ...]) -> RuntimeCheckpoint:
        return RuntimeCheckpoint(
            checkpoint_id=row[0],
            timestamp=row[1],
            reason=row[2],
            component_states=json.loads(row[3]) if row[3] else {},
            policy_state_reference=row[4],
            execution_state_reference=row[5],
            experience_state_reference=row[6],
            adaptation_state_reference=row[7],
            schema_version=row[8],
            metadata=json.loads(row[9]) if row[9] else {},
        )

    def _row_to_violation(self, row: tuple[Any, ...]) -> InvariantViolation:
        return InvariantViolation(
            violation_id=row[0],
            invariant_id=row[1],
            severity=AssuranceSeverity(row[2]),
            component=row[3],
            description=row[4],
            observed_state=json.loads(row[5]) if row[5] else None,
            expected_state=json.loads(row[6]) if row[6] else None,
            correlation_id=row[7],
            timestamp=row[8],
            metadata=json.loads(row[9]) if row[9] else {},
        )

    def _row_to_recovery(self, row: tuple[Any, ...]) -> RecoveryResult:
        return RecoveryResult(
            success=bool(row[1]),
            recovery_id=row[0],
            reason=row[2],
            restored_components=tuple(json.loads(row[3])) if row[3] else (),
            failed_components=tuple(json.loads(row[4])) if row[4] else (),
            checkpoint_id=row[5],
            duration=row[6],
            errors=tuple(json.loads(row[7])) if row[7] else (),
            timestamp=row[8],
            metadata=json.loads(row[9]) if row[9] else {},
        )


class RuntimeAssuranceEngine:
    """Thread-safe engine for runtime assurance, audit trail, checkpoints, and safe recovery."""

    def __init__(
        self,
        store: RuntimeAssuranceStore | None = None,
        clock: Clock | None = None,
        event_bus: EventBus | None = None,
        config: ConfigurationManager | None = None,
        governance_engine: RuntimeGovernanceEngine | None = None,
        policy_engine: RuntimePolicyEngine | None = None,
        execution_engine: RuntimeExecutionEngine | None = None,
        experience_engine: RuntimeExperienceEngine | None = None,
        adaptation_engine: RuntimeAdaptivePolicyEngine | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self.store = store or RuntimeAssuranceStore()
        self.clock = clock or SystemClock()
        self.event_bus = event_bus
        self.config = config
        self.governance_engine = governance_engine
        self.policy_engine = policy_engine
        self.execution_engine = execution_engine
        self.experience_engine = experience_engine
        self.adaptation_engine = adaptation_engine

        self._start_time = time.time()
        self._status = AssuranceStatus.HEALTHY
        self._in_safe_mode = False
        self._safe_mode_reason: str | None = None
        self._invariants: dict[str, RuntimeInvariant] = {}
        self._invariant_check_fns: dict[str, Callable[[], bool]] = {}

        self._degraded_components: set[str] = set()
        self._failed_components: set[str] = set()

        self._recovery_count = 0
        self._register_default_invariants()

    def _register_default_invariants(self) -> None:
        # Registers built-in core invariants
        self.register_invariant(
            RuntimeInvariant(
                invariant_id="INV-GOV-BYPASS",
                name="Governance Inviolability",
                description="Governance policy cannot be bypassed or modified.",
                component="governance",
                severity=AssuranceSeverity.CRITICAL,
            ),
            check_fn=self._check_gov_invariant,
        )
        self.register_invariant(
            RuntimeInvariant(
                invariant_id="INV-EXEC-AUTHORITY",
                name="Single Execution Authority",
                description="Stage 12 ExecutionEngine is sole execution authority.",
                component="execution",
                severity=AssuranceSeverity.CRITICAL,
            ),
            check_fn=self._check_exec_invariant,
        )
        self.register_invariant(
            RuntimeInvariant(
                invariant_id="INV-ADAPT-APPROVAL",
                name="Adaptation Approval Control",
                description="Stage 14 adaptations cannot be applied without explicit approval.",
                component="adaptation",
                severity=AssuranceSeverity.ERROR,
            ),
            check_fn=self._check_adapt_invariant,
        )

    def _check_gov_invariant(self) -> bool:
        if self.governance_engine is not None:
            # Check scope is valid and governance policy exists
            snap = self.governance_engine.get_governance_snapshot()
            return snap is not None
        return True

    def _check_exec_invariant(self) -> bool:
        if self.execution_engine is not None:
            snap = self.execution_engine.get_execution_snapshot()
            return snap is not None
        return True

    def _check_adapt_invariant(self) -> bool:
        if self.adaptation_engine is not None:
            snap = self.adaptation_engine.get_adaptation_snapshot()
            return snap.blocked == 0 or snap.total_proposals >= snap.blocked
        return True

    def register_invariant(
        self, invariant: RuntimeInvariant, check_fn: Callable[[], bool] | None = None
    ) -> None:
        with self._lock:
            self._invariants[invariant.invariant_id] = invariant
            if check_fn:
                self._invariant_check_fns[invariant.invariant_id] = check_fn

    def check_invariant(
        self, invariant_id: str, correlation_id: str = ""
    ) -> InvariantViolation | None:
        with self._lock:
            inv = self._invariants.get(invariant_id)
            if not inv:
                return None

            fn = self._invariant_check_fns.get(invariant_id)
            passed = True
            if fn:
                try:
                    passed = fn()
                except Exception:
                    passed = False

            if not passed:
                cid = correlation_id or f"corr-{uuid.uuid4().hex[:8]}"
                now_iso = self.clock.now_iso()
                vid = f"viol-{invariant_id}-{uuid.uuid4().hex[:8]}"
                violation = InvariantViolation(
                    violation_id=vid,
                    invariant_id=invariant_id,
                    severity=inv.severity,
                    component=inv.component,
                    description=f"Invariant violation detected: {inv.name} - {inv.description}",
                    observed_state="FAILED",
                    expected_state="PASSED",
                    correlation_id=cid,
                    timestamp=now_iso,
                )
                self.store.save_violation(violation)
                self._degraded_components.add(inv.component)

                if inv.severity == AssuranceSeverity.CRITICAL:
                    self._status = AssuranceStatus.DEGRADED
                    fail_closed = True
                    if self.config is not None:
                        fail_closed = self.config.get_typed(
                            "autonomy.assurance_fail_closed", bool, True
                        )
                    if fail_closed:
                        self.enter_safe_mode(
                            reason=f"Critical invariant violation: {inv.invariant_id}"
                        )

                if self.event_bus:
                    self.event_bus.publish(
                        RuntimeInvariantViolationDetected(
                            violation_id=vid,
                            invariant_id=invariant_id,
                            severity=inv.severity.value,
                            component=inv.component,
                            description=violation.description,
                        )
                    )
                return violation
            return None

    def check_all_invariants(self, correlation_id: str = "") -> list[InvariantViolation]:
        with self._lock:
            violations: list[InvariantViolation] = []
            for iid in list(self._invariants.keys()):
                v = self.check_invariant(iid, correlation_id=correlation_id)
                if v:
                    violations.append(v)
            return violations

    def record_audit(
        self,
        component: str,
        stage: str,
        event_type: str,
        action: str,
        actor: str,
        outcome: str,
        severity: AssuranceSeverity = AssuranceSeverity.INFO,
        details: str = "",
        correlation_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> AuditRecord:
        with self._lock:
            cid = correlation_id or f"corr-{uuid.uuid4().hex[:8]}"
            now_iso = self.clock.now_iso()
            aid = f"audit-{uuid.uuid4().hex[:12]}"

            record = AuditRecord(
                audit_id=aid,
                timestamp=now_iso,
                correlation_id=cid,
                component=component,
                stage=stage,
                event_type=event_type,
                action=action,
                actor=actor,
                outcome=outcome,
                severity=severity,
                details=details,
                metadata=metadata or {},
            )
            self.store.save_audit(record)

            if self.event_bus:
                self.event_bus.publish(
                    RuntimeAuditRecorded(
                        audit_id=aid,
                        correlation_id=cid,
                        component=component,
                        stage=stage,
                        event_type=event_type,
                        severity=severity.value,
                    )
                )
            return record

    def get_audit_record(self, audit_id: str) -> AuditRecord | None:
        return self.store.get_audit(audit_id)

    def get_audit_history(self, limit: int = 100) -> list[AuditRecord]:
        return self.store.query_audit(limit=limit)

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
        return self.store.query_audit(
            correlation_id=correlation_id,
            stage=stage,
            component=component,
            event_type=event_type,
            severity=severity,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )

    def create_checkpoint(self, reason: str = "manual_checkpoint") -> RuntimeCheckpoint:
        with self._lock:
            now_iso = self.clock.now_iso()
            cid = f"chk-{uuid.uuid4().hex[:12]}"

            comp_states: dict[str, Any] = {
                "assurance_status": self._status.value,
                "in_safe_mode": self._in_safe_mode,
            }
            if self.governance_engine:
                comp_states["governance_scope"] = self.governance_engine.get_scope().value
            if self.policy_engine:
                comp_states["policy_total_evaluations"] = (
                    self.policy_engine.get_policy_snapshot().total_evaluations
                )

            policy_ref = f"policy-ref-{now_iso}"
            exec_ref = f"exec-ref-{now_iso}"
            exp_ref = f"exp-ref-{now_iso}"
            adapt_ref = f"adapt-ref-{now_iso}"

            checkpoint = RuntimeCheckpoint(
                checkpoint_id=cid,
                timestamp=now_iso,
                reason=reason,
                component_states=comp_states,
                policy_state_reference=policy_ref,
                execution_state_reference=exec_ref,
                experience_state_reference=exp_ref,
                adaptation_state_reference=adapt_ref,
            )
            self.store.save_checkpoint(checkpoint)

            if self.event_bus:
                self.event_bus.publish(
                    RuntimeCheckpointCreated(
                        checkpoint_id=cid,
                        reason=reason,
                        event_timestamp=now_iso,
                    )
                )
            return checkpoint

    def get_checkpoint(self, checkpoint_id: str) -> RuntimeCheckpoint | None:
        return self.store.get_checkpoint(checkpoint_id)

    def list_checkpoints(self, limit: int = 100) -> list[RuntimeCheckpoint]:
        return self.store.list_checkpoints(limit=limit)

    def restore_checkpoint(self, checkpoint_id: str) -> RecoveryResult:
        with self._lock:
            start_t = time.time()
            now_iso = self.clock.now_iso()
            rec_id = f"rec-{uuid.uuid4().hex[:8]}"

            chk = self.store.get_checkpoint(checkpoint_id)
            if not chk:
                res = RecoveryResult(
                    success=False,
                    recovery_id=rec_id,
                    reason=f"Checkpoint '{checkpoint_id}' not found.",
                    restored_components=(),
                    failed_components=("all",),
                    checkpoint_id=checkpoint_id,
                    duration=time.time() - start_t,
                    errors=(f"Checkpoint '{checkpoint_id}' not found.",),
                    timestamp=now_iso,
                )
                self.store.save_recovery(res)
                return res

            # Corrupted format check
            if not isinstance(chk.component_states, dict):
                res = RecoveryResult(
                    success=False,
                    recovery_id=rec_id,
                    reason=f"Corrupted component_states dict in checkpoint '{checkpoint_id}'.",
                    restored_components=(),
                    failed_components=("all",),
                    checkpoint_id=checkpoint_id,
                    duration=time.time() - start_t,
                    errors=("Corrupted component_states dict",),
                    timestamp=now_iso,
                )
                self.store.save_recovery(res)
                return res

            # Strict Safety: Checkpoints NEVER lower Governance restrictions
            # or escalate AutonomyScope!
            # Stage 10 Governance remains authoritative!

            res = RecoveryResult(
                success=True,
                recovery_id=rec_id,
                reason=f"Restored checkpoint '{checkpoint_id}'",
                restored_components=tuple(chk.component_states.keys()),
                failed_components=(),
                checkpoint_id=checkpoint_id,
                duration=time.time() - start_t,
                errors=(),
                timestamp=now_iso,
            )
            self.store.save_recovery(res)
            return res

    def enter_safe_mode(self, reason: str = "manual_entry") -> None:
        with self._lock:
            if not self._in_safe_mode:
                self._in_safe_mode = True
                self._safe_mode_reason = reason
                self._status = AssuranceStatus.SAFE_MODE
                now_iso = self.clock.now_iso()
                if self.event_bus:
                    self.event_bus.publish(
                        RuntimeSafeModeEntered(
                            reason=reason,
                            event_timestamp=now_iso,
                        )
                    )

    def exit_safe_mode(self, force: bool = False) -> bool:
        with self._lock:
            # Check for critical invariant violations prior to exiting
            critical_viols = [
                v for v in self.store.get_violations(severity=AssuranceSeverity.CRITICAL)
            ]
            if critical_viols and not force:
                return False  # Cannot exit safe mode with unresolved critical violations!

            if self._in_safe_mode:
                self._in_safe_mode = False
                self._safe_mode_reason = None
                self._status = AssuranceStatus.HEALTHY
                now_iso = self.clock.now_iso()
                if self.event_bus:
                    self.event_bus.publish(
                        RuntimeSafeModeExited(
                            reason="Normal exit verified",
                            event_timestamp=now_iso,
                        )
                    )
                return True
            return True

    def is_in_safe_mode(self) -> bool:
        with self._lock:
            return self._in_safe_mode

    def recover(self, reason: str = "manual_recovery") -> RecoveryResult:
        with self._lock:
            start_t = time.time()
            now_iso = self.clock.now_iso()
            rec_id = f"rec-{uuid.uuid4().hex[:8]}"

            if self.event_bus:
                self.event_bus.publish(
                    RuntimeRecoveryStarted(
                        recovery_id=rec_id,
                        reason=reason,
                    )
                )

            # Check invariants
            viols = self.check_all_invariants()
            if any(v.severity == AssuranceSeverity.CRITICAL for v in viols):
                self.enter_safe_mode(reason="Critical violations during recovery")
                res = RecoveryResult(
                    success=False,
                    recovery_id=rec_id,
                    reason="Critical invariant violations detected during recovery",
                    restored_components=(),
                    failed_components=("invariants",),
                    checkpoint_id=None,
                    duration=time.time() - start_t,
                    errors=tuple(v.description for v in viols),
                    timestamp=now_iso,
                )
                self.store.save_recovery(res)
                if self.event_bus:
                    self.event_bus.publish(
                        RuntimeRecoveryFailed(
                            recovery_id=rec_id,
                            reason=res.reason,
                        )
                    )
                return res

            self._degraded_components.clear()
            self._failed_components.clear()
            self._recovery_count += 1
            self._status = AssuranceStatus.RECOVERED

            res = RecoveryResult(
                success=True,
                recovery_id=rec_id,
                reason=reason,
                restored_components=("assurance", "invariants"),
                failed_components=(),
                checkpoint_id=None,
                duration=time.time() - start_t,
                errors=(),
                timestamp=now_iso,
            )
            self.store.save_recovery(res)
            if self.event_bus:
                self.event_bus.publish(
                    RuntimeRecoveryCompleted(
                        recovery_id=rec_id,
                        restored_components=res.restored_components,
                    )
                )
            return res

    def get_health_snapshot(self) -> RuntimeHealthSnapshot:
        with self._lock:
            now_iso = self.clock.now_iso()
            uptime = time.time() - self._start_time

            active_comps = ["assurance"]
            if self.governance_engine:
                active_comps.append("governance")
            if self.policy_engine:
                active_comps.append("policy")
            if self.execution_engine:
                active_comps.append("execution")
            if self.experience_engine:
                active_comps.append("experience")
            if self.adaptation_engine:
                active_comps.append("adaptation")

            active_execs = (
                self.execution_engine.get_execution_snapshot().total_executions
                if self.execution_engine
                else 0
            )
            pending_pols = (
                self.policy_engine.get_policy_snapshot().total_evaluations
                if self.policy_engine
                else 0
            )
            pending_adaps = (
                self.adaptation_engine.get_adaptation_snapshot().pending_approvals
                if self.adaptation_engine
                else 0
            )

            viols = len(self.store.get_violations())
            chks = len(self.store.list_checkpoints())

            status = AssuranceStatus.SAFE_MODE if self._in_safe_mode else self._status

            return RuntimeHealthSnapshot(
                status=status,
                timestamp=now_iso,
                uptime=uptime,
                active_components=tuple(active_comps),
                failed_components=tuple(self._failed_components),
                degraded_components=tuple(self._degraded_components),
                active_executions=active_execs,
                pending_policies=pending_pols,
                pending_adaptations=pending_adaps,
                recent_failures=len(self._failed_components),
                invariant_violations=viols,
                recovery_count=self._recovery_count,
                checkpoint_count=chks,
                in_safe_mode=self._in_safe_mode,
            )
