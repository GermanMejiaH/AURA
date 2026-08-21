"""Stage 18 — Reality Integration Audit, Runtime Hardening & Production Validation.

This test suite executes Stage 10-16 components using 100% real dependencies
without artificial mocks or stubs.
"""

from __future__ import annotations

import os
import tempfile
import threading
from typing import Any

import pytest

from aura.autonomy.module import AutonomyModule
from aura.cognition.scheduling import (
    AdaptationStatus,
    AssuranceSeverity,
    AssuranceStatus,
    AutonomyScope,
    ExecutionState,
    RuntimeAction,
    RuntimeAdaptivePolicyEngine,
    RuntimeAssuranceEngine,
    RuntimeExecutionEngine,
    RuntimeGovernanceEngine,
    RuntimeInvariant,
    RuntimeOperationState,
    RuntimeOrchestrationStore,
    RuntimeOrchestrator,
)
from aura.cognition.scheduling.execution import ExecutionContext
from aura.config import ConfigurationManager
from aura.container import DependencyContainer
from aura.events import EventBus
from aura.memory.store import SQLiteMemoryStore

# ============================================================================
# FASE 3 — REAL SYSTEM BOOT & LIFECYCLE TESTS
# ============================================================================


def test_stage18_real_system_boot_lifecycle() -> None:
    """FASE 3: Verify real system boot, initialization, start, execution and shutdown."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "stage18_boot.db")
        config = ConfigurationManager()
        config.set("storage.sqlite_path", db_path)
        config.set("autonomy.enabled", True)

        container = DependencyContainer()
        event_bus = EventBus()
        module = AutonomyModule(container=container, event_bus=event_bus, config=config)

        # 1. Initialize
        module.initialize()
        assert module.orchestrator is not None
        assert module.governance_engine is not None
        assert module.execution_engine is not None
        assert module.assurance_engine is not None

        # 2. Start
        module.start()
        assert module.control_plane is not None
        assert module.control_plane.get_status().value == "RUNNING"

        # 3. Closed loop operation
        op = module.orchestrator.execute_closed_loop(
            action_id="act-boot-01",
            action_fn=lambda: {"res": "OK"},
        )
        assert op.state == RuntimeOperationState.COMPLETED

        # 4. Stop & Shutdown
        module.stop()
        module.shutdown()


# ============================================================================
# FASE 2 & 7 — REAL CLOSED-LOOP TRACING & ORCHESTRATION TESTS
# ============================================================================


def test_stage18_closed_loop_tracing_identifiers() -> None:
    """FASE 7: Verify real operation trace contains all unifiable IDs."""
    adaptation = RuntimeAdaptivePolicyEngine()
    orchestrator = RuntimeOrchestrator(adaptation_engine=adaptation)
    op = orchestrator.execute_closed_loop(
        action_id="act-trace-01",
        goal_id="goal-trace-01",
        action_fn=lambda: True,
    )

    assert op.operation_id.startswith("op-")
    assert op.correlation_id.startswith("corr-")
    assert op.goal_id == "goal-trace-01"
    assert op.action_id == "act-trace-01"
    assert op.execution_id is not None
    assert op.outcome_id is not None
    assert op.adaptation_proposal_id is not None
    assert op.state == RuntimeOperationState.COMPLETED


# ============================================================================
# FASE 4 — STAGE 12 REAL EXECUTION & ROLLBACK TESTS
# ============================================================================


def test_stage18_real_execution_rollback_state() -> None:
    """FASE 4: Verify real execution failure triggers rollback state mutation."""
    execution = RuntimeExecutionEngine()
    step_executed = {"done": False}
    step_rolled_back = {"done": False}

    def real_action(ctx: ExecutionContext) -> Any:
        step_executed["done"] = True
        raise RuntimeError("Simulated database failure during execution")

    def real_rollback(ctx: ExecutionContext) -> bool:
        step_rolled_back["done"] = True
        return True

    action = RuntimeAction(
        action_id="act-fail-01",
        name="FailingAction",
        execute_fn=real_action,
        rollback_fn=real_rollback,
    )

    ctx = ExecutionContext(
        execution_id="exec-fail-01",
        goal_id="goal-01",
        schedule_id="sched-01",
        idempotency_key="idem-fail-01",
        started_at="2026-08-19T20:00:00Z",
    )

    res = execution.execute(action, ctx)

    assert step_executed["done"] is True
    assert step_rolled_back["done"] is True
    assert res.state == ExecutionState.ROLLED_BACK
    assert res.success is False
    assert "Simulated database failure" in str(res.error)


# ============================================================================
# FASE 5 — STAGE 14 REAL ADAPTATION TESTS
# ============================================================================


def test_stage18_adaptation_approval_flow_and_rejection() -> None:
    """FASE 5: Verify APPROVED != APPLIED and REJECTED => ZERO MUTATION with real engine."""
    from aura.cognition.scheduling.adaptation import AdaptationType

    adaptation = RuntimeAdaptivePolicyEngine()
    prop = adaptation.propose_adaptation(
        action_id="act-adapt-01",
        adaptation_type=AdaptationType.REDUCE_FREQUENCY,
        proposed_value="30",
        reason="Load reduction",
    )

    # 1. Direct apply without approval raises PermissionError
    with pytest.raises(PermissionError):
        adaptation.apply_adaptation(prop.proposal_id)

    # 2. Approve
    approved = adaptation.approve_proposal(
        prop.proposal_id, operator_id="op-admin", reason="Approved"
    )
    assert approved.status == AdaptationStatus.APPROVED
    assert approved.applied_at is None  # APPROVED != APPLIED

    # 3. Explicit apply
    applied = adaptation.apply_adaptation(prop.proposal_id)
    assert applied.status == AdaptationStatus.APPLIED
    assert applied.applied_at is not None


def test_stage18_adaptation_rejection_zero_mutation() -> None:
    """FASE 5: Rejection results in status REJECTED with zero runtime state mutation."""
    from aura.cognition.scheduling.adaptation import AdaptationType

    adaptation = RuntimeAdaptivePolicyEngine()
    prop = adaptation.propose_adaptation(
        action_id="act-adapt-02",
        adaptation_type=AdaptationType.REDUCE_FREQUENCY,
        proposed_value="60",
        reason="Test rejection",
    )

    rejected = adaptation.reject_proposal(
        prop.proposal_id, operator_id="op-admin", reason="Security risk"
    )
    assert rejected.status == AdaptationStatus.REJECTED
    assert rejected.applied_at is None


# ============================================================================
# FASE 6 — STAGE 15 REAL ASSURANCE & SAFE MODE TESTS
# ============================================================================


def test_stage18_assurance_safe_mode_enforcement() -> None:
    """FASE 6: SAFE_MODE blocks new operations real-time and resists unauthorized exit."""
    assurance = RuntimeAssuranceEngine()
    orchestrator = RuntimeOrchestrator(assurance_engine=assurance)

    # Force safe mode
    assurance.enter_safe_mode(reason="Critical anomaly")
    assert assurance.is_in_safe_mode() is True

    # Orchestrator blocks before execution
    op = orchestrator.execute_closed_loop(action_id="act-safe-01")
    assert op.state == RuntimeOperationState.BLOCKED
    assert op.assurance_status == AssuranceStatus.SAFE_MODE.value

    # Register invariant violation
    inv = RuntimeInvariant(
        invariant_id="INV-STAGE18",
        name="Critical invariant",
        description="Invariant check",
        component="assurance",
        severity=AssuranceSeverity.CRITICAL,
    )
    assurance.register_invariant(inv, check_fn=lambda: False)
    assurance.check_invariant("INV-STAGE18")

    # Exit safe mode fails without force
    assert assurance.exit_safe_mode(force=False) is False
    assert assurance.is_in_safe_mode() is True


# ============================================================================
# FASE 9 & 10 — REAL PERSISTENCE, RESTART & RECOVERY TESTS
# ============================================================================


def test_stage18_persistence_and_restart_recovery() -> None:
    """FASE 9 & 10: Process crash simulation recovers incomplete operations from SQLite."""
    mem_store = SQLiteMemoryStore(db_path=":memory:")
    store1 = RuntimeOrchestrationStore(store=mem_store)
    orchestrator1 = RuntimeOrchestrator(store=store1)

    # Create operation left in DISPATCHED state
    op = orchestrator1.create_operation(action_id="act-crash-real")

    # Restart with same SQLite backend
    store2 = RuntimeOrchestrationStore(store=mem_store)
    orchestrator2 = RuntimeOrchestrator(store=store2)

    recovered = orchestrator2.recover_incomplete_operations()
    assert len(recovered) == 1
    assert recovered[0].operation_id == op.operation_id
    assert recovered[0].state == RuntimeOperationState.RECOVERY_REQUIRED


# ============================================================================
# FASE 11 — REAL MULTI-THREADED CONCURRENCY TESTS
# ============================================================================


def test_stage18_real_concurrency_multithreaded() -> None:
    """FASE 11: Execute multiple real operations concurrently with zero database corruption."""
    mem_store = SQLiteMemoryStore(db_path=":memory:")
    store = RuntimeOrchestrationStore(store=mem_store)
    governance = RuntimeGovernanceEngine()
    governance.set_authority_scope(AutonomyScope.UNRESTRICTED)

    orchestrator = RuntimeOrchestrator(store=store, governance_engine=governance)
    errors: list[Exception] = []

    def worker(i: int) -> None:
        try:
            orchestrator.execute_closed_loop(action_id=f"act-real-conc-{i}")
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(15)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    assert store.count_operations() == 15
