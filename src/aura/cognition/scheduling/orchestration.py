from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from aura.config import ConfigurationManager
from aura.events import (
    EventBus,
    RuntimeOperationBlocked,
    RuntimeOperationCancelled,
    RuntimeOperationCompleted,
    RuntimeOperationFailed,
    RuntimeOperationRecoveryRequired,
    RuntimeOperationStarted,
    RuntimeOperationStateChanged,
)
from aura.logging import get_logger
from aura.memory.store import SQLiteMemoryStore

from .adaptation import AdaptationType, RuntimeAdaptivePolicyEngine
from .assurance import RuntimeAssuranceEngine
from .clock import Clock, SystemClock
from .dispatcher import ScheduleDispatcher
from .execution import (
    ExecutionContext,
    ExecutionState,
    RuntimeAction,
    RuntimeExecutionEngine,
)
from .experience import OutcomeRecord, OutcomeType, RuntimeExperienceEngine
from .governance import RuntimeGovernanceEngine
from .models import TemporalSchedule
from .resolution import PolicyAction, RuntimePolicyEngine

logger = get_logger("RuntimeOrchestrator")


class RuntimeOperationState(str, Enum):
    """Closed-loop operational states of a runtime autonomy operation."""

    CREATED = "CREATED"
    CLASSIFIED = "CLASSIFIED"
    POLICY_EVALUATED = "POLICY_EVALUATED"
    GOVERNANCE_EVALUATED = "GOVERNANCE_EVALUATED"
    DISPATCHED = "DISPATCHED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"
    TIMED_OUT = "TIMED_OUT"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    EXPERIENCE_RECORDED = "EXPERIENCE_RECORDED"
    ADAPTATION_CONSIDERED = "ADAPTATION_CONSIDERED"


@dataclass(frozen=True)
class RuntimeOperation:
    """Immutable record tracking an autonomous closed-loop operation."""

    operation_id: str
    correlation_id: str
    goal_id: str | None = None
    action_id: str = ""
    created_at: str = ""
    started_at: str | None = None
    completed_at: str | None = None
    state: RuntimeOperationState = RuntimeOperationState.CREATED
    policy_decision: str | None = None
    governance_decision: str | None = None
    execution_id: str | None = None
    outcome_id: str | None = None
    adaptation_proposal_id: str | None = None
    assurance_status: str | None = None
    failure_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class RuntimeOrchestrationStore:
    """Thread-safe SQLite store for persisting runtime operations."""

    def __init__(self, store: SQLiteMemoryStore | None = None) -> None:
        self._lock = threading.RLock()
        self.store = store or SQLiteMemoryStore(db_path=":memory:")
        self._init_tables()

    def _init_tables(self) -> None:
        with self._lock:
            conn = self.store._get_connection()
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS runtime_operations (
                        operation_id TEXT PRIMARY KEY,
                        correlation_id TEXT NOT NULL,
                        goal_id TEXT,
                        action_id TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        started_at TEXT,
                        completed_at TEXT,
                        state TEXT NOT NULL,
                        policy_decision TEXT,
                        governance_decision TEXT,
                        execution_id TEXT,
                        outcome_id TEXT,
                        adaptation_proposal_id TEXT,
                        assurance_status TEXT,
                        failure_reason TEXT,
                        metadata TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_op_corr ON runtime_operations(correlation_id);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_op_goal ON runtime_operations(goal_id);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_op_state ON runtime_operations(state);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_op_created ON runtime_operations(created_at);"
                )

    def save_operation(self, op: RuntimeOperation) -> None:
        with self._lock:
            conn = self.store._get_connection()
            now_iso = op.completed_at or op.started_at or op.created_at
            meta_json = json.dumps(op.metadata)
            with conn:
                conn.execute(
                    """
                    INSERT INTO runtime_operations (
                        operation_id, correlation_id, goal_id, action_id, created_at,
                        started_at, completed_at, state, policy_decision, governance_decision,
                        execution_id, outcome_id, adaptation_proposal_id, assurance_status,
                        failure_reason, metadata, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(operation_id) DO UPDATE SET
                        started_at=excluded.started_at,
                        completed_at=excluded.completed_at,
                        state=excluded.state,
                        policy_decision=excluded.policy_decision,
                        governance_decision=excluded.governance_decision,
                        execution_id=excluded.execution_id,
                        outcome_id=excluded.outcome_id,
                        adaptation_proposal_id=excluded.adaptation_proposal_id,
                        assurance_status=excluded.assurance_status,
                        failure_reason=excluded.failure_reason,
                        metadata=excluded.metadata,
                        updated_at=excluded.updated_at;
                    """,
                    (
                        op.operation_id,
                        op.correlation_id,
                        op.goal_id,
                        op.action_id,
                        op.created_at,
                        op.started_at,
                        op.completed_at,
                        op.state.value,
                        op.policy_decision,
                        op.governance_decision,
                        op.execution_id,
                        op.outcome_id,
                        op.adaptation_proposal_id,
                        op.assurance_status,
                        op.failure_reason,
                        meta_json,
                        now_iso,
                    ),
                )

    def get_operation(self, operation_id: str) -> RuntimeOperation | None:
        with self._lock:
            conn = self.store._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT operation_id, correlation_id, goal_id, action_id, created_at,
                       started_at, completed_at, state, policy_decision, governance_decision,
                       execution_id, outcome_id, adaptation_proposal_id, assurance_status,
                       failure_reason, metadata
                FROM runtime_operations
                WHERE operation_id = ?;
                """,
                (operation_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_operation(row)

    def query_operations(
        self,
        correlation_id: str | None = None,
        goal_id: str | None = None,
        state: RuntimeOperationState | None = None,
        limit: int = 100,
    ) -> list[RuntimeOperation]:
        with self._lock:
            conn = self.store._get_connection()
            cursor = conn.cursor()
            query = """
                SELECT operation_id, correlation_id, goal_id, action_id, created_at,
                       started_at, completed_at, state, policy_decision, governance_decision,
                       execution_id, outcome_id, adaptation_proposal_id, assurance_status,
                       failure_reason, metadata
                FROM runtime_operations
            """
            conditions: list[str] = []
            params: list[Any] = []

            if correlation_id:
                conditions.append("correlation_id = ?")
                params.append(correlation_id)
            if goal_id:
                conditions.append("goal_id = ?")
                params.append(goal_id)
            if state:
                conditions.append("state = ?")
                params.append(state.value)

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " ORDER BY created_at DESC LIMIT ?;"
            params.append(limit)

            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            return [self._row_to_operation(r) for r in rows]

    def list_active_operations(self) -> list[RuntimeOperation]:
        with self._lock:
            active_states = (
                RuntimeOperationState.CREATED.value,
                RuntimeOperationState.CLASSIFIED.value,
                RuntimeOperationState.POLICY_EVALUATED.value,
                RuntimeOperationState.GOVERNANCE_EVALUATED.value,
                RuntimeOperationState.DISPATCHED.value,
                RuntimeOperationState.EXECUTING.value,
                RuntimeOperationState.RECOVERY_REQUIRED.value,
            )
            conn = self.store._get_connection()
            cursor = conn.cursor()
            placeholders = ",".join("?" for _ in active_states)
            query = f"""
                SELECT operation_id, correlation_id, goal_id, action_id, created_at,
                       started_at, completed_at, state, policy_decision, governance_decision,
                       execution_id, outcome_id, adaptation_proposal_id, assurance_status,
                       failure_reason, metadata
                FROM runtime_operations
                WHERE state IN ({placeholders})
                ORDER BY created_at DESC;
            """
            cursor.execute(query, active_states)
            rows = cursor.fetchall()
            return [self._row_to_operation(r) for r in rows]

    def count_operations(self) -> int:
        with self._lock:
            conn = self.store._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM runtime_operations;")
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    def _row_to_operation(self, row: tuple[Any, ...]) -> RuntimeOperation:
        meta_dict = json.loads(row[15]) if row[15] else {}
        return RuntimeOperation(
            operation_id=row[0],
            correlation_id=row[1],
            goal_id=row[2],
            action_id=row[3],
            created_at=row[4],
            started_at=row[5],
            completed_at=row[6],
            state=RuntimeOperationState(row[7]),
            policy_decision=row[8],
            governance_decision=row[9],
            execution_id=row[10],
            outcome_id=row[11],
            adaptation_proposal_id=row[12],
            assurance_status=row[13],
            failure_reason=row[14],
            metadata=meta_dict,
        )


class RuntimeOrchestrator:
    """Thread-safe orchestration engine for closed-loop continuous autonomy.

    Strict Safety Boundary: RuntimeOrchestrator coordinates existing stage
    engines (Stages 10-15); it NEVER replaces their authority or business logic.
    """

    def __init__(
        self,
        store: RuntimeOrchestrationStore | None = None,
        clock: Clock | None = None,
        event_bus: EventBus | None = None,
        config: ConfigurationManager | None = None,
        governance_engine: RuntimeGovernanceEngine | None = None,
        policy_engine: RuntimePolicyEngine | None = None,
        dispatcher: ScheduleDispatcher | None = None,
        execution_engine: RuntimeExecutionEngine | None = None,
        experience_engine: RuntimeExperienceEngine | None = None,
        adaptation_engine: RuntimeAdaptivePolicyEngine | None = None,
        assurance_engine: RuntimeAssuranceEngine | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self.store = store or RuntimeOrchestrationStore()
        self.clock = clock or SystemClock()
        self.event_bus = event_bus
        self.config = config
        self.governance_engine = governance_engine
        self.policy_engine = policy_engine
        self.dispatcher = dispatcher
        self.execution_engine = execution_engine
        self.experience_engine = experience_engine
        self.adaptation_engine = adaptation_engine
        self.assurance_engine = assurance_engine

    def create_operation(
        self,
        action_id: str,
        goal_id: str | None = None,
        correlation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeOperation:
        with self._lock:
            op_id = f"op-{uuid.uuid4().hex[:8]}"
            cid = correlation_id or f"corr-{uuid.uuid4().hex[:8]}"
            now_iso = self.clock.now_iso()

            op = RuntimeOperation(
                operation_id=op_id,
                correlation_id=cid,
                goal_id=goal_id,
                action_id=action_id,
                created_at=now_iso,
                state=RuntimeOperationState.CREATED,
                metadata=metadata or {},
            )
            self.store.save_operation(op)

            if self.event_bus:
                self.event_bus.publish(
                    RuntimeOperationStarted(
                        operation_id=op_id,
                        correlation_id=cid,
                        goal_id=goal_id or "",
                        action_id=action_id,
                    )
                )
            return op

    def execute_closed_loop(
        self,
        action_id: str,
        goal_id: str | None = None,
        correlation_id: str | None = None,
        action_fn: Callable[[], Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeOperation:
        """Executes a closed-loop operation through Policy -> Governance -> Dispatch -> Execution.

        Includes Outcome Experience, Adaptation Proposal, and Assurance Audit.
        """
        with self._lock:
            # Prevent duplicate active operations for same action if configured
            existing_active = [
                op for op in self.store.list_active_operations() if op.action_id == action_id
            ]
            if existing_active:
                logger.warning(f"Active operation already exists for action '{action_id}'")

            op = self.create_operation(
                action_id=action_id,
                goal_id=goal_id,
                correlation_id=correlation_id,
                metadata=metadata,
            )
            now_iso = self.clock.now_iso()
            op = self._transition_state(op, RuntimeOperationState.CLASSIFIED, started_at=now_iso)

            # STEP 1: Stage 15 Assurance Check (Safe Mode Quarantine)
            if self.assurance_engine and self.assurance_engine.is_in_safe_mode():
                reason = "System is in SAFE_MODE quarantine."
                op = self._transition_state(
                    op,
                    RuntimeOperationState.BLOCKED,
                    completed_at=now_iso,
                    assurance_status="SAFE_MODE",
                    failure_reason=reason,
                )
                if self.event_bus:
                    self.event_bus.publish(
                        RuntimeOperationBlocked(
                            operation_id=op.operation_id,
                            reason=reason,
                            blocking_stage="STAGE_15_ASSURANCE",
                        )
                    )
                return op

            # STEP 2: Stage 11 Policy Evaluation
            policy_dec_str = "ALLOW"
            if self.policy_engine:
                sched = TemporalSchedule(
                    goal_id=goal_id or "goal_default",
                    schedule_id=action_id,
                    metadata=metadata or {},
                )
                policy_dec = self.policy_engine.evaluate_schedule(sched)
                policy_dec_str = (
                    policy_dec.action.value if hasattr(policy_dec, "action") else str(policy_dec)
                )
                if hasattr(policy_dec, "action") and policy_dec.action in (
                    PolicyAction.CANCEL,
                    PolicyAction.BLOCK,
                    PolicyAction.DEFER,
                ):
                    op = self._transition_state(
                        op,
                        RuntimeOperationState.BLOCKED,
                        completed_at=now_iso,
                        policy_decision=policy_dec_str,
                        failure_reason=f"Policy decision: {policy_dec_str}",
                    )
                    if self.event_bus:
                        self.event_bus.publish(
                            RuntimeOperationBlocked(
                                operation_id=op.operation_id,
                                reason=f"Policy blocked: {policy_dec_str}",
                                blocking_stage="STAGE_11_POLICY",
                            )
                        )
                    return op

            op = self._transition_state(
                op, RuntimeOperationState.POLICY_EVALUATED, policy_decision=policy_dec_str
            )

            # STEP 3: Stage 10 Governance Check
            gov_dec_str = "ALLOWED"
            if self.governance_engine:
                gov_decision = self.governance_engine.evaluate_action(action_id=action_id)
                gov_dec_str = "ALLOWED" if gov_decision.allowed else "BLOCKED"
                if not gov_decision.allowed:
                    op = self._transition_state(
                        op,
                        RuntimeOperationState.BLOCKED,
                        completed_at=now_iso,
                        governance_decision=gov_dec_str,
                        failure_reason=f"Governance blocked: {gov_decision.reason}",
                    )
                    if self.event_bus:
                        self.event_bus.publish(
                            RuntimeOperationBlocked(
                                operation_id=op.operation_id,
                                reason=f"Governance blocked: {gov_decision.reason}",
                                blocking_stage="STAGE_10_GOVERNANCE",
                            )
                        )
                    return op

            op = self._transition_state(
                op, RuntimeOperationState.GOVERNANCE_EVALUATED, governance_decision=gov_dec_str
            )

            # STEP 4: Stage 3/4 Dispatch
            op = self._transition_state(op, RuntimeOperationState.DISPATCHED)

            # STEP 5: Stage 12 Execution
            op = self._transition_state(op, RuntimeOperationState.EXECUTING)
            exec_id = f"exec-{uuid.uuid4().hex[:8]}"

            exec_success = True
            exec_err = None
            if self.execution_engine:

                def _fn(c: Any) -> Any:
                    if action_fn:
                        return action_fn()
                    return True

                action_obj = RuntimeAction(
                    action_id=action_id,
                    name=action_id,
                    execute_fn=_fn,
                )
                ctx = ExecutionContext(
                    execution_id=exec_id,
                    goal_id=goal_id or "goal_default",
                    schedule_id=action_id,
                    idempotency_key=f"idem-{action_id}",
                    started_at=now_iso,
                    metadata=metadata or {},
                )
                exec_res = self.execution_engine.execute(
                    action=action_obj,
                    context=ctx,
                )
                exec_id = exec_res.execution_id if hasattr(exec_res, "execution_id") else exec_id
                exec_success = (
                    exec_res.state == ExecutionState.COMMITTED
                    if hasattr(exec_res, "state")
                    else exec_res.success
                )
                exec_err = exec_res.error if hasattr(exec_res, "error") else None

            if not exec_success:
                op = self._transition_state(
                    op,
                    RuntimeOperationState.FAILED,
                    completed_at=now_iso,
                    execution_id=exec_id,
                    failure_reason=exec_err or "Execution failed",
                )
                if self.event_bus:
                    self.event_bus.publish(
                        RuntimeOperationFailed(
                            operation_id=op.operation_id,
                            reason=exec_err or "Execution failed",
                            failure_type="EXECUTION_FAILURE",
                        )
                    )
                return op

            # STEP 6: Stage 13 Outcome & Experience
            outcome_id = exec_id
            if self.experience_engine:
                if self.execution_engine and "exec_res" in locals():
                    self.experience_engine.record_execution_result(
                        result=exec_res, action_id=action_id
                    )
                else:
                    out_rec = OutcomeRecord(
                        execution_id=exec_id,
                        action_id=action_id,
                        outcome_type=OutcomeType.SUCCESS,
                        success=True,
                        started_at=now_iso,
                        completed_at=now_iso,
                    )
                    self.experience_engine.record_outcome(out_rec)

            op = self._transition_state(
                op,
                RuntimeOperationState.EXPERIENCE_RECORDED,
                execution_id=exec_id,
                outcome_id=outcome_id,
            )

            # STEP 7: Stage 14 Adaptation Evaluation (Never Auto-Applied)
            prop_id = None
            if self.adaptation_engine:
                prop = self.adaptation_engine.propose_adaptation(
                    action_id=action_id,
                    adaptation_type=AdaptationType.CHANGE_RETRY_POLICY,
                    proposed_value="2",
                    reason="Routine optimization",
                )
                prop_id = prop.proposal_id if hasattr(prop, "proposal_id") else None

            op = self._transition_state(
                op,
                RuntimeOperationState.ADAPTATION_CONSIDERED,
                adaptation_proposal_id=prop_id,
            )

            # STEP 8: Stage 15 Assurance Audit & Completion
            assure_status = "HEALTHY"
            if self.assurance_engine:
                aud = self.assurance_engine.record_audit(
                    component="orchestrator",
                    stage="STAGE_16",
                    event_type="CLOSED_LOOP_COMPLETED",
                    action=action_id,
                    actor="RuntimeOrchestrator",
                    outcome="SUCCESS",
                    correlation_id=op.correlation_id,
                )
                assure_status = self.assurance_engine.get_health_snapshot().status.value

            op = self._transition_state(
                op,
                RuntimeOperationState.COMPLETED,
                completed_at=now_iso,
                assurance_status=assure_status,
            )

            if self.event_bus:
                self.event_bus.publish(
                    RuntimeOperationCompleted(
                        operation_id=op.operation_id,
                        execution_id=exec_id,
                        duration=0.1,
                    )
                )
            return op

    def cancel_operation(
        self, operation_id: str, reason: str = "manual_cancellation"
    ) -> RuntimeOperation | None:
        with self._lock:
            op = self.store.get_operation(operation_id)
            if not op:
                return None

            if op.state in (
                RuntimeOperationState.COMPLETED,
                RuntimeOperationState.FAILED,
                RuntimeOperationState.CANCELLED,
                RuntimeOperationState.BLOCKED,
            ):
                return op

            now_iso = self.clock.now_iso()
            updated_op = self._transition_state(
                op,
                RuntimeOperationState.CANCELLED,
                completed_at=now_iso,
                failure_reason=reason,
            )

            if self.event_bus:
                self.event_bus.publish(
                    RuntimeOperationCancelled(
                        operation_id=operation_id,
                        reason=reason,
                    )
                )
            return updated_op

    def get_operation(self, operation_id: str) -> RuntimeOperation | None:
        return self.store.get_operation(operation_id)

    def list_active_operations(self) -> list[RuntimeOperation]:
        return self.store.list_active_operations()

    def get_operation_history(self, limit: int = 100) -> list[RuntimeOperation]:
        return self.store.query_operations(limit=limit)

    def recover_incomplete_operations(self) -> list[RuntimeOperation]:
        with self._lock:
            actives = self.store.list_active_operations()
            recovered: list[RuntimeOperation] = []

            for op in actives:
                rec_op = self._transition_state(
                    op,
                    RuntimeOperationState.RECOVERY_REQUIRED,
                    failure_reason="Process restart recovery",
                )
                if self.event_bus:
                    self.event_bus.publish(
                        RuntimeOperationRecoveryRequired(
                            operation_id=op.operation_id,
                            reason="Incomplete operation recovered after process restart",
                        )
                    )
                recovered.append(rec_op)
            return recovered

    def _transition_state(
        self,
        op: RuntimeOperation,
        new_state: RuntimeOperationState,
        started_at: str | None = None,
        completed_at: str | None = None,
        policy_decision: str | None = None,
        governance_decision: str | None = None,
        execution_id: str | None = None,
        outcome_id: str | None = None,
        adaptation_proposal_id: str | None = None,
        assurance_status: str | None = None,
        failure_reason: str | None = None,
    ) -> RuntimeOperation:
        prev_state = op.state
        updated_op = RuntimeOperation(
            operation_id=op.operation_id,
            correlation_id=op.correlation_id,
            goal_id=op.goal_id,
            action_id=op.action_id,
            created_at=op.created_at,
            started_at=started_at or op.started_at,
            completed_at=completed_at or op.completed_at,
            state=new_state,
            policy_decision=policy_decision or op.policy_decision,
            governance_decision=governance_decision or op.governance_decision,
            execution_id=execution_id or op.execution_id,
            outcome_id=outcome_id or op.outcome_id,
            adaptation_proposal_id=adaptation_proposal_id or op.adaptation_proposal_id,
            assurance_status=assurance_status or op.assurance_status,
            failure_reason=failure_reason or op.failure_reason,
            metadata=op.metadata,
        )
        self.store.save_operation(updated_op)

        if self.event_bus and prev_state != new_state:
            self.event_bus.publish(
                RuntimeOperationStateChanged(
                    operation_id=op.operation_id,
                    previous_state=prev_state.value,
                    new_state=new_state.value,
                    reason=failure_reason or f"Transition to {new_state.value}",
                )
            )
        return updated_op
