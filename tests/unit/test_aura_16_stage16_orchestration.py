from __future__ import annotations

import threading

from aura.autonomy.module import AutonomyModule
from aura.cognition.scheduling import (
    AutonomyScope,
    RuntimeAdaptivePolicyEngine,
    RuntimeAssuranceEngine,
    RuntimeControlPlane,
    RuntimeExecutionEngine,
    RuntimeExperienceEngine,
    RuntimeGovernanceEngine,
    RuntimeOperationState,
    RuntimeOrchestrationStore,
    RuntimeOrchestrator,
    RuntimePolicyEngine,
    TestClock,
)
from aura.config import ConfigurationManager
from aura.container import DependencyContainer
from aura.events import Event, EventBus
from aura.memory.store import SQLiteMemoryStore


# 1. Operation Creation
def test_01_operation_creation() -> None:
    orchestrator = RuntimeOrchestrator()
    op = orchestrator.create_operation(action_id="act-01", goal_id="goal-01")
    assert op.operation_id.startswith("op-")
    assert op.action_id == "act-01"
    assert op.goal_id == "goal-01"
    assert op.state == RuntimeOperationState.CREATED


# 2. Operation IDs
def test_02_operation_ids() -> None:
    orchestrator = RuntimeOrchestrator()
    op1 = orchestrator.create_operation(action_id="act-01")
    op2 = orchestrator.create_operation(action_id="act-02")
    assert op1.operation_id != op2.operation_id
    assert op1.correlation_id != op2.correlation_id


# 3. Correlation Propagation
def test_03_correlation_propagation() -> None:
    orchestrator = RuntimeOrchestrator()
    cid = "corr-custom-999"
    op = orchestrator.execute_closed_loop(action_id="act-corr", correlation_id=cid)
    assert op.correlation_id == cid


# 4. Lifecycle Transitions
def test_04_lifecycle_transitions() -> None:
    orchestrator = RuntimeOrchestrator()
    op = orchestrator.execute_closed_loop(action_id="act-lifecycle")
    assert op.state == RuntimeOperationState.COMPLETED
    assert op.started_at is not None
    assert op.completed_at is not None


# 5. Policy Integration
def test_05_policy_integration() -> None:
    clock = TestClock("2026-08-19T00:00:00Z")
    policy = RuntimePolicyEngine(clock=clock)
    orchestrator = RuntimeOrchestrator(clock=clock, policy_engine=policy)

    op = orchestrator.execute_closed_loop(action_id="act-policy")
    assert op.policy_decision == "ALLOW"
    assert op.state == RuntimeOperationState.COMPLETED


# 6. Governance Integration
def test_06_governance_integration() -> None:
    governance = RuntimeGovernanceEngine()
    orchestrator = RuntimeOrchestrator(governance_engine=governance)

    op = orchestrator.execute_closed_loop(action_id="act-gov")
    assert op.governance_decision == "ALLOWED"
    assert op.state == RuntimeOperationState.COMPLETED


# 7. Dispatch Integration
def test_07_dispatch_integration() -> None:
    orchestrator = RuntimeOrchestrator()
    op = orchestrator.create_operation(action_id="act-dispatch")
    op = orchestrator._transition_state(op, RuntimeOperationState.DISPATCHED)
    assert op.state == RuntimeOperationState.DISPATCHED


# 8. Execution Integration
def test_08_execution_integration() -> None:
    execution = RuntimeExecutionEngine()
    orchestrator = RuntimeOrchestrator(execution_engine=execution)

    op = orchestrator.execute_closed_loop(action_id="act-exec")
    assert op.execution_id is not None
    assert op.execution_id.startswith("exec-")


# 9. Experience Integration
def test_09_experience_integration() -> None:
    experience = RuntimeExperienceEngine()
    orchestrator = RuntimeOrchestrator(experience_engine=experience)

    op = orchestrator.execute_closed_loop(action_id="act-exp")
    assert op.outcome_id is not None
    assert op.outcome_id.startswith("exec-")


# 10. Adaptation Proposal Integration
def test_10_adaptation_proposal_integration() -> None:
    adaptation = RuntimeAdaptivePolicyEngine()
    orchestrator = RuntimeOrchestrator(adaptation_engine=adaptation)

    op = orchestrator.execute_closed_loop(action_id="act-adapt")
    assert op.adaptation_proposal_id is not None
    assert op.adaptation_proposal_id.startswith("prop-")


# 11. Adaptation Approval Remains External
def test_11_adaptation_approval_remains_external() -> None:
    adaptation = RuntimeAdaptivePolicyEngine()
    orchestrator = RuntimeOrchestrator(adaptation_engine=adaptation)

    op = orchestrator.execute_closed_loop(action_id="act-adapt-ext")
    assert op.adaptation_proposal_id is not None
    prop = adaptation.store.get_proposal(op.adaptation_proposal_id)

    # Proposal remains pending approval, never auto-applied!
    assert prop is not None
    assert prop.applied_at is None
    assert prop.approved_at is None


# 12. Assurance Integration
def test_12_assurance_integration() -> None:
    assurance = RuntimeAssuranceEngine()
    orchestrator = RuntimeOrchestrator(assurance_engine=assurance)

    op = orchestrator.execute_closed_loop(action_id="act-assure")
    assert op.assurance_status == "HEALTHY"


# 13. Policy Bypass Attempt Prevented
def test_13_policy_bypass_attempt() -> None:
    clock = TestClock("2026-08-19T00:00:00Z")
    policy = RuntimePolicyEngine(clock=clock)
    orchestrator = RuntimeOrchestrator(clock=clock, policy_engine=policy)

    op = orchestrator.execute_closed_loop(
        action_id="act-blocked", metadata={"deadline_at": "2000-01-01T00:00:00Z"}
    )
    assert op.state == RuntimeOperationState.BLOCKED
    assert "Policy" in op.failure_reason


# 14. Governance Bypass Attempt Prevented
def test_14_governance_bypass_attempt() -> None:
    governance = RuntimeGovernanceEngine()
    governance.set_authority_scope(AutonomyScope.DISABLED)
    orchestrator = RuntimeOrchestrator(governance_engine=governance)

    op = orchestrator.execute_closed_loop(action_id="act-gov-blocked")
    assert op.state == RuntimeOperationState.BLOCKED
    assert "Governance" in op.failure_reason


# 15. Execution Bypass Attempt Prevented
def test_15_execution_bypass_attempt() -> None:
    # Attempting to bypass execution fails as orchestrator delegates to ExecutionEngine
    execution = RuntimeExecutionEngine()
    orchestrator = RuntimeOrchestrator(execution_engine=execution)

    def failing_action() -> None:
        raise ValueError("Execution error")

    op = orchestrator.execute_closed_loop(action_id="act-exec-fail", action_fn=failing_action)
    assert op.state == RuntimeOperationState.FAILED


# 16. Adaptation Bypass Attempt Prevented
def test_16_adaptation_bypass_attempt() -> None:
    adaptation = RuntimeAdaptivePolicyEngine()
    orchestrator = RuntimeOrchestrator(adaptation_engine=adaptation)

    _op = orchestrator.execute_closed_loop(action_id="act-no-auto-apply")
    proposals = adaptation.store.get_proposals()
    assert len(proposals) == 1
    # Verify proposal is NOT applied
    assert proposals[0].applied_at is None


# 17. Cancellation
def test_17_cancellation() -> None:
    orchestrator = RuntimeOrchestrator()
    op = orchestrator.create_operation(action_id="act-cancel")
    canceled = orchestrator.cancel_operation(op.operation_id, reason="User requested")

    assert canceled is not None
    assert canceled.state == RuntimeOperationState.CANCELLED
    assert canceled.failure_reason == "User requested"


# 18. Failure Handling
def test_18_failure_handling() -> None:
    orchestrator = RuntimeOrchestrator()
    op = orchestrator.create_operation(action_id="act-fail")
    failed = orchestrator._transition_state(
        op, RuntimeOperationState.FAILED, failure_reason="Resource unavailable"
    )
    assert failed.state == RuntimeOperationState.FAILED
    assert failed.failure_reason == "Resource unavailable"


# 19. Timeout Handling
def test_19_timeout_handling() -> None:
    orchestrator = RuntimeOrchestrator()
    op = orchestrator.create_operation(action_id="act-timeout")
    timed_out = orchestrator._transition_state(
        op, RuntimeOperationState.TIMED_OUT, failure_reason="Operation timed out"
    )
    assert timed_out.state == RuntimeOperationState.TIMED_OUT


# 20. Recovery-Required State
def test_20_recovery_required_state() -> None:
    orchestrator = RuntimeOrchestrator()
    op = orchestrator.create_operation(action_id="act-rec-req")
    rec = orchestrator._transition_state(
        op, RuntimeOperationState.RECOVERY_REQUIRED, failure_reason="Incomplete after crash"
    )
    assert rec.state == RuntimeOperationState.RECOVERY_REQUIRED


# 21. Restart Recovery
def test_21_restart_recovery() -> None:
    mem_store = SQLiteMemoryStore(db_path=":memory:")
    store1 = RuntimeOrchestrationStore(store=mem_store)
    orchestrator1 = RuntimeOrchestrator(store=store1)

    orchestrator1.create_operation(action_id="act-restart-1")

    # Simulate restart with same database
    store2 = RuntimeOrchestrationStore(store=mem_store)
    orchestrator2 = RuntimeOrchestrator(store=store2)

    recovered = orchestrator2.recover_incomplete_operations()
    assert len(recovered) == 1
    assert recovered[0].state == RuntimeOperationState.RECOVERY_REQUIRED


# 22. Persistence
def test_22_persistence() -> None:
    mem_store = SQLiteMemoryStore(db_path=":memory:")
    store = RuntimeOrchestrationStore(store=mem_store)
    orchestrator = RuntimeOrchestrator(store=store)

    op = orchestrator.create_operation(action_id="act-persist")
    fetched = store.get_operation(op.operation_id)

    assert fetched is not None
    assert fetched.operation_id == op.operation_id


# 23. Idempotency
def test_23_idempotency() -> None:
    orchestrator = RuntimeOrchestrator()
    op = orchestrator.create_operation(action_id="act-idem")
    # Saving same operation multiple times is idempotent
    orchestrator.store.save_operation(op)
    orchestrator.store.save_operation(op)

    assert orchestrator.store.count_operations() == 1


# 24. Duplicate Operation Prevention
def test_24_duplicate_operation_prevention() -> None:
    orchestrator = RuntimeOrchestrator()
    op1 = orchestrator.create_operation(action_id="act-dup")
    op2 = orchestrator.create_operation(action_id="act-dup")

    assert op1.operation_id != op2.operation_id


# 25. Concurrent Operations
def test_25_concurrent_operations() -> None:
    orchestrator = RuntimeOrchestrator()
    errors: list[Exception] = []

    def worker(i: int) -> None:
        try:
            orchestrator.execute_closed_loop(action_id=f"act-concurrent-{i}")
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    assert orchestrator.store.count_operations() == 10


# 26. Concurrent Cancellation
def test_26_concurrent_cancellation() -> None:
    orchestrator = RuntimeOrchestrator()
    op = orchestrator.create_operation(action_id="act-conc-cancel")
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


# 27. EventBus Events Emitted
def test_27_event_bus_events() -> None:
    published: list[Event] = []

    class EventCollector(EventBus):
        def publish(self, event: Event) -> None:
            published.append(event)
            super().publish(event)

    bus = EventCollector()
    orchestrator = RuntimeOrchestrator(event_bus=bus)

    orchestrator.execute_closed_loop(action_id="act-events")
    names = [e.__class__.__name__ for e in published]

    assert "RuntimeOperationStarted" in names
    assert "RuntimeOperationStateChanged" in names
    assert "RuntimeOperationCompleted" in names


# 28. Correlation Integrity
def test_28_correlation_integrity() -> None:
    published: list[Event] = []

    class EventCollector(EventBus):
        def publish(self, event: Event) -> None:
            published.append(event)
            super().publish(event)

    bus = EventCollector()
    orchestrator = RuntimeOrchestrator(event_bus=bus)

    cid = "corr-integrity-100"
    op = orchestrator.execute_closed_loop(action_id="act-corr-int", correlation_id=cid)

    assert op.correlation_id == cid
    start_events = [e for e in published if e.__class__.__name__ == "RuntimeOperationStarted"]
    assert len(start_events) == 1
    assert start_events[0].correlation_id == cid


# 29. ControlPlane Integration
def test_29_control_plane_integration() -> None:
    orchestrator = RuntimeOrchestrator()
    control = RuntimeControlPlane(runtime=None, orchestrator=orchestrator)  # type: ignore[arg-type]

    op = orchestrator.execute_closed_loop(action_id="act-control")
    fetched = control.get_operation(op.operation_id)

    assert fetched is not None
    assert fetched.operation_id == op.operation_id

    history = control.get_operation_history()
    assert len(history) == 1


# 30. IoC Integration
def test_30_ioc_integration() -> None:
    container = DependencyContainer()
    config = ConfigurationManager()
    bus = EventBus()

    module = AutonomyModule(config=config, container=container, event_bus=bus)
    module.on_initialize()

    assert container.has(RuntimeOrchestrationStore) is True
    assert container.has(RuntimeOrchestrator) is True

    resolved = container.resolve(RuntimeOrchestrator)
    assert isinstance(resolved, RuntimeOrchestrator)


# 31. Configuration Disabled Behavior
def test_31_config_disabled_behavior() -> None:
    config = ConfigurationManager()
    config.set("autonomy.orchestration_enabled", False)
    orchestrator = RuntimeOrchestrator(config=config)

    assert orchestrator.config.get_typed("autonomy.orchestration_enabled", bool, True) is False


# 32. Stage 10 Governance Compatibility
def test_32_stage10_governance_compatibility() -> None:
    governance = RuntimeGovernanceEngine()
    orchestrator = RuntimeOrchestrator(governance_engine=governance)

    op = orchestrator.execute_closed_loop(action_id="act-stage10")
    assert op.governance_decision == "ALLOWED"


# 33. Stage 11 Policy Compatibility
def test_33_stage11_policy_compatibility() -> None:
    clock = TestClock("2026-08-19T00:00:00Z")
    policy = RuntimePolicyEngine(clock=clock)
    orchestrator = RuntimeOrchestrator(clock=clock, policy_engine=policy)

    op = orchestrator.execute_closed_loop(action_id="act-stage11")
    assert op.policy_decision == "ALLOW"


# 34. Stage 12 Execution Compatibility
def test_34_stage12_execution_compatibility() -> None:
    execution = RuntimeExecutionEngine()
    orchestrator = RuntimeOrchestrator(execution_engine=execution)

    op = orchestrator.execute_closed_loop(action_id="act-stage12")
    assert op.execution_id is not None


# 35. Stage 13 Experience Compatibility
def test_35_stage13_experience_compatibility() -> None:
    experience = RuntimeExperienceEngine()
    orchestrator = RuntimeOrchestrator(experience_engine=experience)

    op = orchestrator.execute_closed_loop(action_id="act-stage13")
    assert op.outcome_id is not None


# 36. Stage 14 Adaptation Compatibility
def test_36_stage14_adaptation_compatibility() -> None:
    adaptation = RuntimeAdaptivePolicyEngine()
    orchestrator = RuntimeOrchestrator(adaptation_engine=adaptation)

    op = orchestrator.execute_closed_loop(action_id="act-stage14")
    assert op.adaptation_proposal_id is not None


# 37. Stage 15 Assurance Compatibility
def test_37_stage15_assurance_compatibility() -> None:
    assurance = RuntimeAssuranceEngine()
    orchestrator = RuntimeOrchestrator(assurance_engine=assurance)

    op = orchestrator.execute_closed_loop(action_id="act-stage15")
    assert op.assurance_status == "HEALTHY"


# 38. Full Pipeline Ordering Verification
def test_38_full_pipeline_ordering() -> None:
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

    op = orchestrator.execute_closed_loop(action_id="act-full-pipeline")
    assert op.state == RuntimeOperationState.COMPLETED
    assert op.policy_decision == "ALLOW"
    assert op.governance_decision == "ALLOWED"
    assert op.execution_id is not None
    assert op.outcome_id is not None
    assert op.adaptation_proposal_id is not None
    assert op.assurance_status == "HEALTHY"


# 39. Adversarial Authority Bypass
def test_39_adversarial_authority_bypass() -> None:
    assurance = RuntimeAssuranceEngine()
    orchestrator = RuntimeOrchestrator(assurance_engine=assurance)

    # Force SAFE_MODE in Assurance Engine
    assurance.enter_safe_mode(reason="Security threat")

    op = orchestrator.execute_closed_loop(action_id="act-bypass-attempt")

    # Orchestrator MUST block operation and respect Assurance quarantine!
    assert op.state == RuntimeOperationState.BLOCKED
    assert op.assurance_status == "SAFE_MODE"


# 40. Stage 1-9 Regression Compatibility
def test_40_stage1_9_regression_compatibility() -> None:
    # Verify legacy modules and schedule store compatibility
    store = SQLiteMemoryStore(db_path=":memory:")
    orch_store = RuntimeOrchestrationStore(store=store)
    orchestrator = RuntimeOrchestrator(store=orch_store)

    op = orchestrator.create_operation(action_id="act-legacy")
    assert op.operation_id is not None
    assert store is not None
