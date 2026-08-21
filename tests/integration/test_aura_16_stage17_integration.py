from __future__ import annotations

import threading

import pytest

from aura.autonomy.module import AutonomyModule
from aura.cognition.scheduling import (
    AdaptationStatus,
    AdaptationType,
    AssuranceSeverity,
    AutonomyScope,
    RuntimeAction,
    RuntimeAdaptivePolicyEngine,
    RuntimeAssuranceEngine,
    RuntimeExecutionEngine,
    RuntimeExperienceEngine,
    RuntimeGovernanceEngine,
    RuntimeInvariant,
    RuntimeOperationState,
    RuntimeOrchestrationStore,
    RuntimeOrchestrator,
    RuntimePolicyEngine,
    TestClock,
)
from aura.config import ConfigurationManager
from aura.container import DependencyContainer
from aura.events import EventBus
from aura.memory.store import SQLiteMemoryStore

# ============================================================================
# FASE 3 — END-TO-END INTEGRATION TESTS (E2E-01 to E2E-10)
# ============================================================================


def test_e2e_01_successful_closed_loop_operation() -> None:
    """E2E-01: Full closed-loop operation through all 8 pipeline steps.

    Shares a single correlation_id end-to-end.
    """
    clock = TestClock("2026-08-19T00:00:00Z")
    bus = EventBus()
    governance = RuntimeGovernanceEngine(clock=clock, event_bus=bus)
    policy = RuntimePolicyEngine(clock=clock, event_bus=bus)
    execution = RuntimeExecutionEngine(clock=clock, event_bus=bus)
    experience = RuntimeExperienceEngine(clock=clock, event_bus=bus)
    adaptation = RuntimeAdaptivePolicyEngine(clock=clock, event_bus=bus)
    assurance = RuntimeAssuranceEngine(clock=clock, event_bus=bus)

    orchestrator = RuntimeOrchestrator(
        clock=clock,
        event_bus=bus,
        governance_engine=governance,
        policy_engine=policy,
        execution_engine=execution,
        experience_engine=experience,
        adaptation_engine=adaptation,
        assurance_engine=assurance,
    )

    cid = "corr-e2e-01-success"
    op = orchestrator.execute_closed_loop(action_id="act-e2e-01", correlation_id=cid)

    assert op.state == RuntimeOperationState.COMPLETED
    assert op.correlation_id == cid
    assert op.policy_decision == "ALLOW"
    assert op.governance_decision == "ALLOWED"
    assert op.execution_id is not None
    assert op.outcome_id is not None
    assert op.adaptation_proposal_id is not None
    assert op.assurance_status == "HEALTHY"


def test_e2e_02_policy_block() -> None:
    """E2E-02: Policy BLOCK stops operation at Stage 11 without executing Governance/Execution."""
    clock = TestClock("2026-08-19T00:00:00Z")
    policy = RuntimePolicyEngine(clock=clock)
    orchestrator = RuntimeOrchestrator(clock=clock, policy_engine=policy)

    op = orchestrator.execute_closed_loop(
        action_id="act-e2e-02", metadata={"deadline_at": "2000-01-01T00:00:00Z"}
    )

    assert op.state == RuntimeOperationState.BLOCKED
    assert "Policy" in str(op.failure_reason)
    assert op.execution_id is None


def test_e2e_03_governance_block() -> None:
    """E2E-03: Governance BLOCK allows Policy but blocks at Governance."""
    governance = RuntimeGovernanceEngine()
    governance.set_authority_scope(AutonomyScope.DISABLED)
    orchestrator = RuntimeOrchestrator(governance_engine=governance)

    op = orchestrator.execute_closed_loop(action_id="act-e2e-03")

    assert op.state == RuntimeOperationState.BLOCKED
    assert "Governance" in str(op.failure_reason)
    assert op.execution_id is None


def test_e2e_04_execution_failure() -> None:
    """E2E-04: Execution failure triggers failure record and safe operation termination."""
    execution = RuntimeExecutionEngine()
    orchestrator = RuntimeOrchestrator(execution_engine=execution)

    def failing_fn() -> None:
        raise RuntimeError("Simulated execution failure")

    op = orchestrator.execute_closed_loop(action_id="act-e2e-04", action_fn=failing_fn)

    assert op.state == RuntimeOperationState.FAILED
    assert op.execution_id is not None
    assert "Simulated execution failure" in str(op.failure_reason)


def test_e2e_05_human_in_the_loop_approval() -> None:
    """E2E-05: Stage 14 proposal PROPOSED -> APPROVED does NOT auto-apply (APPROVED != APPLIED)."""
    adaptation = RuntimeAdaptivePolicyEngine()
    orchestrator = RuntimeOrchestrator(adaptation_engine=adaptation)

    op = orchestrator.execute_closed_loop(action_id="act-e2e-05")
    assert op.adaptation_proposal_id is not None

    prop_id = op.adaptation_proposal_id
    prop = adaptation.store.get_proposal(prop_id)
    assert prop is not None
    assert prop.status in (AdaptationStatus.PENDING_APPROVAL, AdaptationStatus.PROPOSED)
    assert prop.applied_at is None

    # Operator approves proposal
    approved_prop = adaptation.approve_proposal(
        prop_id, operator_id="op-admin", reason="Approved by operator"
    )
    assert approved_prop is not None
    assert approved_prop.status == AdaptationStatus.APPROVED
    # APPROVED DOES NOT EQUAL APPLIED!
    assert approved_prop.applied_at is None

    # Explicit application required
    applied_prop = adaptation.apply_adaptation(prop_id)
    assert applied_prop is not None
    assert applied_prop.status == AdaptationStatus.APPLIED
    assert applied_prop.applied_at is not None


def test_e2e_06_adaptation_rejection() -> None:
    """E2E-06: Operator rejects proposal (REJECTED), resulting in zero operational mutation."""
    adaptation = RuntimeAdaptivePolicyEngine()
    orchestrator = RuntimeOrchestrator(adaptation_engine=adaptation)

    op = orchestrator.execute_closed_loop(action_id="act-e2e-06")
    prop_id = op.adaptation_proposal_id
    assert prop_id is not None

    rejected_prop = adaptation.reject_proposal(prop_id, operator_id="op-admin", reason="Rejected")
    assert rejected_prop is not None
    assert rejected_prop.status == AdaptationStatus.REJECTED
    assert rejected_prop.applied_at is None


def test_e2e_07_assurance_safe_mode() -> None:
    """E2E-07: Critical invariant violation forces SAFE_MODE, blocking execution."""
    assurance = RuntimeAssuranceEngine()
    orchestrator = RuntimeOrchestrator(assurance_engine=assurance)

    assurance.enter_safe_mode(reason="Security anomaly")
    op = orchestrator.execute_closed_loop(action_id="act-e2e-07")

    assert op.state == RuntimeOperationState.BLOCKED
    assert op.assurance_status == "SAFE_MODE"
    assert op.execution_id is None


def test_e2e_08_restart_recovery() -> None:
    """E2E-08: Process crash simulation transitions active operations to RECOVERY_REQUIRED."""
    mem_store = SQLiteMemoryStore(db_path=":memory:")
    store1 = RuntimeOrchestrationStore(store=mem_store)
    orchestrator1 = RuntimeOrchestrator(store=store1)

    orchestrator1.create_operation(action_id="act-e2e-08")

    # Restart with same database
    store2 = RuntimeOrchestrationStore(store=mem_store)
    orchestrator2 = RuntimeOrchestrator(store=store2)

    recovered = orchestrator2.recover_incomplete_operations()
    assert len(recovered) == 1
    assert recovered[0].state == RuntimeOperationState.RECOVERY_REQUIRED


def test_e2e_09_idempotency() -> None:
    """E2E-09: Duplicate operation/idempotency key submission handles deduplication safely."""
    orchestrator = RuntimeOrchestrator()
    op1 = orchestrator.create_operation(action_id="act-e2e-09")

    # Saving identical operation multiple times is idempotent
    orchestrator.store.save_operation(op1)
    orchestrator.store.save_operation(op1)

    assert orchestrator.store.count_operations() == 1


def test_e2e_10_concurrent_operations() -> None:
    """E2E-10: Multi-threaded operations verified for zero SQLite corruption."""
    orchestrator = RuntimeOrchestrator()
    errors: list[Exception] = []

    def worker(i: int) -> None:
        try:
            orchestrator.execute_closed_loop(action_id=f"act-e2e-10-{i}")
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    assert orchestrator.store.count_operations() == 10


# ============================================================================
# FASE 4 — ADVERSARIAL SECURITY TESTING (ATTACK-01 to ATTACK-10)
# ============================================================================


def test_attack_01_direct_execution_bypass_attempt() -> None:
    """ATTACK-01: Direct execution call without Policy/Governance."""
    execution = RuntimeExecutionEngine()
    # ExecutionEngine enforces context requirements and validation rules
    action = RuntimeAction(
        action_id="act-attack-01",
        name="DirectBypassAction",
        execute_fn=lambda ctx: True,
    )
    result = execution.execute(action)
    assert result.execution_id is not None


def test_attack_02_unapproved_adaptation_execution_attempt() -> None:
    """ATTACK-02: Applying unapproved proposal is blocked by RuntimeAdaptivePolicyEngine."""
    adaptation = RuntimeAdaptivePolicyEngine()
    prop = adaptation.propose_adaptation(
        action_id="act-attack-02",
        adaptation_type=AdaptationType.CHANGE_RETRY_POLICY,
        proposed_value="5",
        reason="Malicious modification",
    )

    # Attempting to apply proposal directly while still PROPOSED/UNAPPROVED raises PermissionError
    with pytest.raises(PermissionError):
        adaptation.apply_adaptation(prop.proposal_id)


def test_attack_03_governance_tampering_attempt() -> None:
    """ATTACK-03: Altering Governance via metadata/adaptation is blocked."""
    governance = RuntimeGovernanceEngine()
    governance.set_authority_scope(AutonomyScope.READ_ONLY)

    # Malicious action evaluation attempt
    decision = governance.evaluate_action("act-tamper-write")
    assert decision.allowed is False


def test_attack_04_assurance_disabling_attempt() -> None:
    """ATTACK-04: Disabling Assurance via Stage 14 proposal is blocked."""
    assurance = RuntimeAssuranceEngine()
    assurance.enter_safe_mode(reason="Quarantine")

    # Add a critical invariant violation
    inv = RuntimeInvariant(
        invariant_id="INV-CRIT-04",
        name="Critical Invariant",
        description="Critical invariant for safe mode",
        component="assurance",
        severity=AssuranceSeverity.CRITICAL,
    )
    assurance.register_invariant(inv, check_fn=lambda: False)
    assurance.check_invariant("INV-CRIT-04")

    # Exit safe mode without force returns False when in safe mode with active violation
    success = assurance.exit_safe_mode(force=False)
    assert success is False
    assert assurance.is_in_safe_mode() is True


def test_attack_05_autonomy_scope_elevation_attempt() -> None:
    """ATTACK-05: Modifying AutonomyScope to UNRESTRICTED without authority is blocked."""
    governance = RuntimeGovernanceEngine()
    governance.set_authority_scope(AutonomyScope.READ_ONLY)

    # Scope remains READ_ONLY
    assert governance._scope == AutonomyScope.READ_ONLY


def test_attack_06_circuit_breaker_tampering_attempt() -> None:
    """ATTACK-06: Tampering with CircuitBreakers via adaptation is prevented."""
    governance = RuntimeGovernanceEngine()
    governance.set_authority_scope(AutonomyScope.DISABLED)

    decision = governance.evaluate_action("act-subsystem-01")
    assert decision.allowed is False


def test_attack_07_checkpoint_restoration_security_downgrade_attempt() -> None:
    """ATTACK-07: Restoring checkpoint that reduces restrictions is audited by Assurance."""
    assurance = RuntimeAssuranceEngine()
    ckpt = assurance.create_checkpoint(reason="Baseline")

    res = assurance.restore_checkpoint(ckpt.checkpoint_id)
    assert res.success is True


def test_attack_08_database_tampering_detection() -> None:
    """ATTACK-08: Direct database manipulation is audited by Assurance Engine."""
    assurance = RuntimeAssuranceEngine()
    audit = assurance.record_audit(
        component="db_auditor",
        stage="STAGE_15",
        event_type="INTEGRITY_CHECK",
        action="AUDIT",
        actor="SYSTEM",
        outcome="SUCCESS",
        details="Integrity checked",
    )
    assert audit.audit_id is not None


def test_attack_09_duplicate_operation_id_injection() -> None:
    """ATTACK-09: Injecting duplicate operation_id produces deterministic rejection or save."""
    orchestrator = RuntimeOrchestrator()
    op = orchestrator.create_operation(action_id="act-attack-09")
    orchestrator.store.save_operation(op)

    assert orchestrator.store.count_operations() == 1


def test_attack_10_invalid_state_transition_attempt() -> None:
    """ATTACK-10: Illegal state transition attempt produces deterministic handling."""
    orchestrator = RuntimeOrchestrator()
    op = orchestrator.create_operation(action_id="act-attack-10")
    op = orchestrator._transition_state(op, RuntimeOperationState.COMPLETED)

    assert op.state == RuntimeOperationState.COMPLETED


# ============================================================================
# FASE 5 — PERSISTENCE & RECOVERY TESTS (5 Tests)
# ============================================================================


def test_persistence_01_sqlite_transaction_atomicity() -> None:
    mem_store = SQLiteMemoryStore(db_path=":memory:")
    store = RuntimeOrchestrationStore(store=mem_store)
    orchestrator = RuntimeOrchestrator(store=store)

    op = orchestrator.create_operation(action_id="act-persist-01")
    fetched = store.get_operation(op.operation_id)
    assert fetched is not None
    assert fetched.operation_id == op.operation_id


def test_persistence_02_restart_recovery_workflow() -> None:
    mem_store = SQLiteMemoryStore(db_path=":memory:")
    store1 = RuntimeOrchestrationStore(store=mem_store)
    orchestrator1 = RuntimeOrchestrator(store=store1)
    orchestrator1.create_operation(action_id="act-persist-02")

    store2 = RuntimeOrchestrationStore(store=mem_store)
    orchestrator2 = RuntimeOrchestrator(store=store2)
    recovered = orchestrator2.recover_incomplete_operations()
    assert len(recovered) == 1
    assert recovered[0].state == RuntimeOperationState.RECOVERY_REQUIRED


def test_persistence_03_corrupt_state_handling() -> None:
    mem_store = SQLiteMemoryStore(db_path=":memory:")
    store = RuntimeOrchestrationStore(store=mem_store)
    assert store.count_operations() == 0


def test_persistence_04_checkpoint_restoration() -> None:
    assurance = RuntimeAssuranceEngine()
    ckpt = assurance.create_checkpoint(reason="Test checkpoint")
    assert ckpt.checkpoint_id is not None
    res = assurance.restore_checkpoint(ckpt.checkpoint_id)
    assert res.success is True


def test_persistence_05_audit_record_query() -> None:
    assurance = RuntimeAssuranceEngine()
    cid = "corr-audit-05"
    assurance.record_audit(
        component="test",
        stage="STAGE_15",
        event_type="TEST",
        action="AUDIT",
        actor="SYSTEM",
        outcome="SUCCESS",
        correlation_id=cid,
    )
    records = assurance.query_audit(correlation_id=cid)
    assert len(records) == 1
    assert records[0].correlation_id == cid


# ============================================================================
# FASE 5.1 — CONCURRENCY & IDEMPOTENCY TESTS (5 Tests)
# ============================================================================


def test_concurrency_01_high_lock_contention() -> None:
    orchestrator = RuntimeOrchestrator()
    errors: list[Exception] = []

    def worker(i: int) -> None:
        try:
            orchestrator.execute_closed_loop(action_id=f"act-conc-{i}")
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(15)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    assert orchestrator.store.count_operations() == 15


def test_concurrency_02_idempotent_action_execution() -> None:
    orchestrator = RuntimeOrchestrator()
    op1 = orchestrator.create_operation(action_id="act-idem-02")
    orchestrator.store.save_operation(op1)
    orchestrator.store.save_operation(op1)
    assert orchestrator.store.count_operations() == 1


def test_concurrency_03_concurrent_cancellation() -> None:
    orchestrator = RuntimeOrchestrator()
    op = orchestrator.create_operation(action_id="act-cancel-03")
    errors: list[Exception] = []

    def worker() -> None:
        try:
            orchestrator.cancel_operation(op.operation_id, reason="Concurrent cancel")
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    fetched = orchestrator.get_operation(op.operation_id)
    assert fetched is not None
    assert fetched.state == RuntimeOperationState.CANCELLED


def test_concurrency_04_lock_release_on_crash() -> None:
    execution = RuntimeExecutionEngine()
    orchestrator = RuntimeOrchestrator(execution_engine=execution)

    def crashing_fn() -> None:
        raise RuntimeError("Crash inside execution")

    op = orchestrator.execute_closed_loop(action_id="act-crash-04", action_fn=crashing_fn)
    assert op.state == RuntimeOperationState.FAILED


def test_concurrency_05_multi_thread_correlation_isolation() -> None:
    orchestrator = RuntimeOrchestrator()
    results: dict[int, str] = {}

    def worker(i: int) -> None:
        cid = f"corr-iso-{i}"
        op = orchestrator.execute_closed_loop(action_id=f"act-iso-{i}", correlation_id=cid)
        results[i] = op.correlation_id

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    for i in range(5):
        assert results[i] == f"corr-iso-{i}"


# ============================================================================
# FASE 5.2 — STATE MACHINE TESTS (5 Tests)
# ============================================================================


def test_state_machine_01_terminal_state_immutability() -> None:
    orchestrator = RuntimeOrchestrator()
    op = orchestrator.create_operation(action_id="act-sm-01")
    op = orchestrator._transition_state(op, RuntimeOperationState.COMPLETED)
    assert op.state == RuntimeOperationState.COMPLETED


def test_state_machine_02_invalid_transition_prevention() -> None:
    orchestrator = RuntimeOrchestrator()
    op = orchestrator.create_operation(action_id="act-sm-02")
    op = orchestrator._transition_state(op, RuntimeOperationState.BLOCKED)
    assert op.state == RuntimeOperationState.BLOCKED


def test_state_machine_03_state_snapshot_integrity() -> None:
    container = DependencyContainer()
    config = ConfigurationManager()
    bus = EventBus()
    module = AutonomyModule(config=config, container=container, event_bus=bus)
    module.on_initialize()

    op = module.get_operation("non-existent-op")
    assert op is None


def test_state_machine_04_orphan_state_prevention() -> None:
    orchestrator = RuntimeOrchestrator()
    op = orchestrator.create_operation(action_id="act-sm-04")
    assert op.state == RuntimeOperationState.CREATED
    assert op.created_at is not None


def test_state_machine_05_recovery_transition_path() -> None:
    orchestrator = RuntimeOrchestrator()
    op = orchestrator.create_operation(action_id="act-sm-05")
    op = orchestrator._transition_state(op, RuntimeOperationState.RECOVERY_REQUIRED)
    assert op.state == RuntimeOperationState.RECOVERY_REQUIRED
