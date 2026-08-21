from __future__ import annotations

import threading

from aura.autonomy.module import AutonomyModule
from aura.cognition.scheduling import (
    AdaptationPolicy,
    AdaptationProposal,
    AdaptationStatus,
    AdaptationType,
    AutonomyScope,
    ExperienceConfidence,
    ExperienceRecommendation,
    RecommendationType,
    RuntimeAction,
    RuntimeAdaptationStore,
    RuntimeAdaptationValidator,
    RuntimeAdaptivePolicyEngine,
    RuntimeControlPlane,
    RuntimeExecutionEngine,
    RuntimeExperienceEngine,
    RuntimeGovernanceEngine,
    RuntimePolicyEngine,
    TestClock,
)
from aura.config import ConfigurationManager
from aura.container import DependencyContainer
from aura.events import (
    Event,
    EventBus,
)
from aura.memory.store import SQLiteMemoryStore


# 1. Initial Adaptation State
def test_01_initial_adaptation_state() -> None:
    engine = RuntimeAdaptivePolicyEngine()
    snap = engine.get_adaptation_snapshot()
    assert snap.total_proposals == 0
    assert snap.pending_approvals == 0
    assert snap.approved == 0
    assert snap.applied == 0
    assert snap.rolled_back == 0


# 2. Proposal Creation
def test_02_proposal_creation() -> None:
    engine = RuntimeAdaptivePolicyEngine()
    prop = engine.propose_adaptation(
        action_id="act-01",
        adaptation_type=AdaptationType.REDUCE_FREQUENCY,
        proposed_value=30,
        current_value=60,
        reason="Repeated timeouts",
    )
    assert prop.proposal_id.startswith("prop-act-01")
    assert prop.status in (AdaptationStatus.PENDING_APPROVAL, AdaptationStatus.PROPOSED)
    assert prop.proposed_value == 30


# 3. Proposal Immutability
def test_03_proposal_immutability() -> None:
    engine = RuntimeAdaptivePolicyEngine()
    prop = engine.propose_adaptation(
        action_id="act-immut",
        adaptation_type=AdaptationType.REDUCE_FREQUENCY,
        proposed_value=20,
        reason="Testing immutability",
    )
    try:
        prop.proposed_value = 10  # type: ignore[misc]
        raise AssertionError("AdaptationProposal should be frozen/immutable")
    except AttributeError:
        pass


# 4. Recommendation to Proposal Conversion
def test_04_recommendation_to_proposal() -> None:
    engine = RuntimeAdaptivePolicyEngine()
    rec = ExperienceRecommendation(
        action_id="act-rec",
        recommendation_type=RecommendationType.REDUCE_FREQUENCY,
        confidence=ExperienceConfidence.HIGH,
        reason="High failure rate observed",
        supporting_execution_count=10,
        generated_at="2026-08-19T00:00:00Z",
    )
    prop = engine.create_proposal_from_recommendation(rec)
    assert prop is not None
    assert prop.action_id == "act-rec"
    assert prop.adaptation_type == AdaptationType.REDUCE_FREQUENCY


# 5. Validation Success
def test_05_validation_success() -> None:
    validator = RuntimeAdaptationValidator()
    prop = AdaptationProposal(
        proposal_id="p-val-succ",
        action_id="act-normal",
        adaptation_type=AdaptationType.REDUCE_FREQUENCY,
        current_value=60,
        proposed_value=40,
        reason="Valid frequency reduction",
        source_recommendation="TEST",
        source_experience_count=5,
        confidence="HIGH",
        created_at="2026-08-19T00:00:00Z",
        expires_at="2099-01-01T00:00:00Z",
    )
    res = validator.validate(prop)
    assert res.valid is True
    assert len(res.violations) == 0


# 6. Validation Failure
def test_06_validation_failure() -> None:
    validator = RuntimeAdaptationValidator()
    # Reduction by 80% (60 -> 10) exceeds max reduction of 50%
    prop = AdaptationProposal(
        proposal_id="p-val-fail",
        action_id="act-normal",
        adaptation_type=AdaptationType.REDUCE_FREQUENCY,
        current_value=60,
        proposed_value=10,
        reason="Excessive frequency reduction",
        source_recommendation="TEST",
        source_experience_count=5,
        confidence="HIGH",
        created_at="2026-08-19T00:00:00Z",
        expires_at="2099-01-01T00:00:00Z",
    )
    res = validator.validate(prop)
    assert res.valid is False
    assert any("exceeds maximum allowed" in v for v in res.violations)


# 7. Confidence Validation
def test_07_confidence_validation() -> None:
    engine = RuntimeAdaptivePolicyEngine()
    prop = engine.propose_adaptation(
        action_id="act-conf",
        adaptation_type=AdaptationType.REDUCE_FREQUENCY,
        proposed_value=40,
        current_value=60,
        reason="Confidence test",
        confidence="LOW",
    )
    assert prop.confidence == "LOW"


# 8. Safety Bound Enforcement
def test_08_safety_bound_enforcement() -> None:
    policy = AdaptationPolicy(max_frequency_reduction_percent=25.0)
    validator = RuntimeAdaptationValidator(policy=policy)
    engine = RuntimeAdaptivePolicyEngine(validator=validator)

    # Reduction from 100 to 50 is 50% (exceeds policy limit 25%)
    prop = engine.propose_adaptation(
        action_id="act-bound",
        adaptation_type=AdaptationType.REDUCE_FREQUENCY,
        current_value=100,
        proposed_value=50,
        reason="Bound test",
    )
    assert prop.status == AdaptationStatus.REJECTED


# 9. Proposal Expiration
def test_09_proposal_expiration() -> None:
    clock = TestClock("2026-08-19T00:00:00Z")
    engine = RuntimeAdaptivePolicyEngine(clock=clock)

    prop = engine.propose_adaptation(
        action_id="act-exp",
        adaptation_type=AdaptationType.REDUCE_FREQUENCY,
        proposed_value=40,
        current_value=60,
        reason="Expiration test",
    )

    # Advance clock beyond expiration (TTL 3600s)
    clock.advance(3601)

    try:
        engine.approve_proposal(prop.proposal_id, operator_id="op1", reason="Late approval")
        raise AssertionError("Expected ValueError for expired proposal")
    except ValueError as exc:
        assert "expired" in str(exc)


# 10. Operator Approval
def test_10_operator_approval() -> None:
    engine = RuntimeAdaptivePolicyEngine()
    prop = engine.propose_adaptation(
        action_id="act-appr",
        adaptation_type=AdaptationType.REQUIRE_OPERATOR_REVIEW,
        proposed_value="REVIEWED",
        reason="Approval test",
    )

    approved_prop = engine.approve_proposal(
        prop.proposal_id, operator_id="admin_user", reason="Approved after review"
    )
    assert approved_prop.status == AdaptationStatus.APPROVED
    assert approved_prop.operator_id == "admin_user"


# 11. Operator Rejection
def test_11_operator_rejection() -> None:
    engine = RuntimeAdaptivePolicyEngine()
    prop = engine.propose_adaptation(
        action_id="act-rej",
        adaptation_type=AdaptationType.REQUIRE_OPERATOR_REVIEW,
        proposed_value="REVIEWED",
        reason="Rejection test",
    )

    rejected_prop = engine.reject_proposal(
        prop.proposal_id, operator_id="admin_user", reason="Denied by security policy"
    )
    assert rejected_prop.status == AdaptationStatus.REJECTED


# 12. Approval Does Not Automatically Apply
def test_12_approval_does_not_automatically_apply() -> None:
    engine = RuntimeAdaptivePolicyEngine()
    prop = engine.propose_adaptation(
        action_id="act-noauto",
        adaptation_type=AdaptationType.REQUIRE_OPERATOR_REVIEW,
        proposed_value="REVIEWED",
        reason="No auto-apply test",
    )

    approved_prop = engine.approve_proposal(
        prop.proposal_id, operator_id="admin_user", reason="Approved"
    )
    assert approved_prop.status == AdaptationStatus.APPROVED
    # Proposal remains APPROVED and NOT APPLIED!
    fetched = engine.store.get_proposal(prop.proposal_id)
    assert fetched is not None
    assert fetched.status == AdaptationStatus.APPROVED


# 13. Apply Approved Proposal
def test_13_apply_approved_proposal() -> None:
    engine = RuntimeAdaptivePolicyEngine()
    prop = engine.propose_adaptation(
        action_id="act-apply",
        adaptation_type=AdaptationType.REDUCE_FREQUENCY,
        current_value=60,
        proposed_value=40,
        reason="Apply test",
    )
    engine.approve_proposal(prop.proposal_id, operator_id="admin_user", reason="Approved")

    applied_prop = engine.apply_adaptation(prop.proposal_id)
    assert applied_prop.status == AdaptationStatus.APPLIED
    assert applied_prop.applied_at is not None


# 14. Apply Without Approval Blocked
def test_14_apply_without_approval_blocked() -> None:
    engine = RuntimeAdaptivePolicyEngine()
    prop = engine.propose_adaptation(
        action_id="act-unappr",
        adaptation_type=AdaptationType.REQUIRE_OPERATOR_REVIEW,
        proposed_value="VAL",
        reason="Unapproved apply test",
    )

    try:
        engine.apply_adaptation(prop.proposal_id)
        raise AssertionError("Expected PermissionError when applying unapproved proposal")
    except PermissionError:
        pass


# 15. Apply Expired Proposal Blocked
def test_15_apply_expired_proposal_blocked() -> None:
    clock = TestClock("2026-08-19T00:00:00Z")
    engine = RuntimeAdaptivePolicyEngine(clock=clock)
    prop = engine.propose_adaptation(
        action_id="act-exp-app",
        adaptation_type=AdaptationType.REDUCE_FREQUENCY,
        current_value=60,
        proposed_value=40,
        reason="Expired apply test",
    )
    engine.approve_proposal(prop.proposal_id, operator_id="op1", reason="Approved in time")

    clock.advance(3601)  # Expire proposal

    try:
        engine.apply_adaptation(prop.proposal_id)
        raise AssertionError("Expected ValueError for applying expired proposal")
    except ValueError as exc:
        assert "expired" in str(exc)


# 16. Idempotent Apply
def test_16_idempotent_apply() -> None:
    engine = RuntimeAdaptivePolicyEngine()
    prop = engine.propose_adaptation(
        action_id="act-idemp-app",
        adaptation_type=AdaptationType.REDUCE_FREQUENCY,
        current_value=60,
        proposed_value=40,
        reason="Idempotent apply test",
    )
    engine.approve_proposal(prop.proposal_id, operator_id="op1", reason="Approved")

    app1 = engine.apply_adaptation(prop.proposal_id)
    app2 = engine.apply_adaptation(prop.proposal_id)
    assert app1.status == AdaptationStatus.APPLIED
    assert app2.status == AdaptationStatus.APPLIED
    assert app1.applied_at == app2.applied_at


# 17. Rollback
def test_17_rollback() -> None:
    engine = RuntimeAdaptivePolicyEngine()
    prop = engine.propose_adaptation(
        action_id="act-rb",
        adaptation_type=AdaptationType.REDUCE_FREQUENCY,
        current_value=60,
        proposed_value=40,
        reason="Rollback test",
    )
    engine.approve_proposal(prop.proposal_id, operator_id="op1", reason="Approved")
    engine.apply_adaptation(prop.proposal_id)

    rolled_prop = engine.rollback_adaptation(prop.proposal_id)
    assert rolled_prop.status == AdaptationStatus.ROLLED_BACK
    assert rolled_prop.rolled_back_at is not None


# 18. Idempotent Rollback
def test_18_idempotent_rollback() -> None:
    engine = RuntimeAdaptivePolicyEngine()
    prop = engine.propose_adaptation(
        action_id="act-idemp-rb",
        adaptation_type=AdaptationType.REDUCE_FREQUENCY,
        current_value=60,
        proposed_value=40,
        reason="Idempotent rollback test",
    )
    engine.approve_proposal(prop.proposal_id, operator_id="op1", reason="Approved")
    engine.apply_adaptation(prop.proposal_id)

    rb1 = engine.rollback_adaptation(prop.proposal_id)
    rb2 = engine.rollback_adaptation(prop.proposal_id)
    assert rb1.status == AdaptationStatus.ROLLED_BACK
    assert rb2.status == AdaptationStatus.ROLLED_BACK


# 19. Invalid Rollback Blocked
def test_19_invalid_rollback_blocked() -> None:
    engine = RuntimeAdaptivePolicyEngine()
    prop = engine.propose_adaptation(
        action_id="act-inv-rb",
        adaptation_type=AdaptationType.REDUCE_FREQUENCY,
        proposed_value=40,
        reason="Invalid rollback test",
    )
    # Proposal is PENDING_APPROVAL, not APPLIED!
    try:
        engine.rollback_adaptation(prop.proposal_id)
        raise AssertionError("Expected ValueError when rolling back non-applied proposal")
    except ValueError:
        pass


# 20. Governance Modification Blocked
def test_20_governance_modification_blocked() -> None:
    engine = RuntimeAdaptivePolicyEngine()
    prop = engine.propose_adaptation(
        action_id="act-gov-tamper",
        adaptation_type=AdaptationType.DISABLE_ACTION,
        proposed_value="DISABLE",
        reason="Governance tamper test",
        metadata={"modify_governance": True},
    )
    assert prop.status == AdaptationStatus.BLOCKED


# 21. Circuit Breaker Modification Blocked
def test_21_circuit_breaker_modification_blocked() -> None:
    engine = RuntimeAdaptivePolicyEngine()
    prop = engine.propose_adaptation(
        action_id="act-cb-tamper",
        adaptation_type=AdaptationType.CHANGE_RESOURCE_LIMIT,
        proposed_value="RESET",
        reason="Circuit breaker tamper test",
        metadata={"tamper_circuit_breaker": True},
    )
    assert prop.status == AdaptationStatus.BLOCKED


# 22. Autonomy Scope Modification Blocked
def test_22_autonomy_scope_modification_blocked() -> None:
    engine = RuntimeAdaptivePolicyEngine()
    prop = engine.propose_adaptation(
        action_id="act-scope-tamper",
        adaptation_type=AdaptationType.ENABLE_ACTION,
        proposed_value="UNRESTRICTED",
        reason="Scope escalation test",
    )
    assert prop.status == AdaptationStatus.BLOCKED


# 23. Policy Bypass Blocked
def test_23_policy_bypass_blocked() -> None:
    engine = RuntimeAdaptivePolicyEngine()
    prop = engine.propose_adaptation(
        action_id="act-pol-bypass",
        adaptation_type=AdaptationType.CHANGE_PRIORITY,
        proposed_value="CRITICAL",
        reason="Policy bypass test",
        metadata={"bypass_policy_engine": True},
    )
    assert prop.status == AdaptationStatus.BLOCKED


# 24. Execution Bypass Blocked
def test_24_execution_bypass_blocked() -> None:
    engine = RuntimeAdaptivePolicyEngine()
    prop = engine.propose_adaptation(
        action_id="act-exec-bypass",
        adaptation_type=AdaptationType.ENABLE_ACTION,
        proposed_value="EXECUTE",
        reason="Execution bypass test",
        metadata={"direct_execution_invocation": True},
    )
    assert prop.status == AdaptationStatus.BLOCKED


# 25. Concurrent Proposal Creation
def test_25_concurrent_proposal_creation() -> None:
    engine = RuntimeAdaptivePolicyEngine()
    errors: list[Exception] = []

    def worker(i: int) -> None:
        try:
            engine.propose_adaptation(
                action_id=f"act-conc-{i}",
                adaptation_type=AdaptationType.REDUCE_FREQUENCY,
                current_value=60,
                proposed_value=40,
                reason=f"Concurrent creation test {i}",
            )
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    assert engine.store.count() == 20


# 26. Concurrent Approval
def test_26_concurrent_approval() -> None:
    engine = RuntimeAdaptivePolicyEngine()
    prop = engine.propose_adaptation(
        action_id="act-conc-appr",
        adaptation_type=AdaptationType.REQUIRE_OPERATOR_REVIEW,
        proposed_value="VAL",
        reason="Concurrent approval test",
    )

    errors: list[Exception] = []

    def worker(i: int) -> None:
        try:
            engine.approve_proposal(prop.proposal_id, operator_id=f"op_{i}", reason="Approve")
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    assert engine.store.get_proposal(prop.proposal_id).status == AdaptationStatus.APPROVED


# 27. Concurrent Apply
def test_27_concurrent_apply() -> None:
    engine = RuntimeAdaptivePolicyEngine()
    prop = engine.propose_adaptation(
        action_id="act-conc-apply",
        adaptation_type=AdaptationType.REDUCE_FREQUENCY,
        current_value=60,
        proposed_value=40,
        reason="Concurrent apply test",
    )
    engine.approve_proposal(prop.proposal_id, operator_id="op1", reason="Approve")

    errors: list[Exception] = []

    def worker() -> None:
        try:
            engine.apply_adaptation(prop.proposal_id)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    assert engine.store.get_proposal(prop.proposal_id).status == AdaptationStatus.APPLIED


# 28. SQLite Persistence Integration
def test_28_sqlite_persistence() -> None:
    mem_store = SQLiteMemoryStore(db_path=":memory:")
    adapt_store = RuntimeAdaptationStore(store=mem_store)
    engine = RuntimeAdaptivePolicyEngine(store=adapt_store)

    prop = engine.propose_adaptation(
        action_id="act-sql",
        adaptation_type=AdaptationType.REDUCE_FREQUENCY,
        current_value=60,
        proposed_value=40,
        reason="SQL persistence test",
    )
    assert adapt_store.count() == 1
    fetched = adapt_store.get_proposal(prop.proposal_id)
    assert fetched is not None
    assert fetched.action_id == "act-sql"


# 29. Persistence Recovery After Restart
def test_29_persistence_recovery_after_restart() -> None:
    mem_store = SQLiteMemoryStore(db_path=":memory:")
    store1 = RuntimeAdaptationStore(store=mem_store)
    engine1 = RuntimeAdaptivePolicyEngine(store=store1)

    prop = engine1.propose_adaptation(
        action_id="act-restart",
        adaptation_type=AdaptationType.REDUCE_FREQUENCY,
        current_value=60,
        proposed_value=40,
        reason="Restart test",
    )
    engine1.approve_proposal(prop.proposal_id, operator_id="op1", reason="Approve")

    # Simulate restart with new store wrapping same DB
    store2 = RuntimeAdaptationStore(store=mem_store)
    engine2 = RuntimeAdaptivePolicyEngine(store=store2)

    fetched = engine2.store.get_proposal(prop.proposal_id)
    assert fetched is not None
    assert fetched.status == AdaptationStatus.APPROVED


# 30. EventBus Events Publishing
def test_30_event_bus_events() -> None:
    published: list[Event] = []

    class EventCollector(EventBus):
        def publish(self, event: Event) -> None:
            published.append(event)
            super().publish(event)

    bus = EventCollector()
    engine = RuntimeAdaptivePolicyEngine(event_bus=bus)

    prop = engine.propose_adaptation(
        action_id="act-events",
        adaptation_type=AdaptationType.REDUCE_FREQUENCY,
        current_value=60,
        proposed_value=40,
        reason="Events test",
    )
    engine.approve_proposal(prop.proposal_id, operator_id="op1", reason="Approve")
    engine.apply_adaptation(prop.proposal_id)
    engine.rollback_adaptation(prop.proposal_id)

    names = [e.__class__.__name__ for e in published]
    assert "RuntimeAdaptationProposed" in names
    assert "RuntimeAdaptationValidationPassed" in names
    assert "RuntimeAdaptationApproved" in names
    assert "RuntimeAdaptationApplied" in names
    assert "RuntimeAdaptationRolledBack" in names


# 31. ControlPlane Integration
def test_31_control_plane_integration() -> None:
    engine = RuntimeAdaptivePolicyEngine()
    control = RuntimeControlPlane(runtime=None, adaptation_engine=engine)  # type: ignore[arg-type]

    prop = control.adaptation_engine.propose_adaptation(  # type: ignore[union-attr]
        action_id="act-cp",
        adaptation_type=AdaptationType.REQUIRE_OPERATOR_REVIEW,
        proposed_value="VAL",
        reason="CP test",
    )

    pending = control.get_pending_adaptations("act-cp")
    assert len(pending) == 1

    app_prop = control.approve_adaptation(
        prop.proposal_id, operator_id="op_cp", reason="Approve CP"
    )
    assert app_prop.status == AdaptationStatus.APPROVED

    applied_prop = control.apply_adaptation(prop.proposal_id)
    assert applied_prop.status == AdaptationStatus.APPLIED


# 32. AutonomyModule IoC Integration
def test_32_autonomy_module_ioc_integration() -> None:
    container = DependencyContainer()
    config = ConfigurationManager()
    bus = EventBus()

    module = AutonomyModule(config=config, container=container, event_bus=bus)
    module.on_initialize()

    assert container.has(RuntimeAdaptationStore) is True
    assert container.has(RuntimeAdaptivePolicyEngine) is True

    resolved = container.resolve(RuntimeAdaptivePolicyEngine)
    assert isinstance(resolved, RuntimeAdaptivePolicyEngine)

    snap = module.get_adaptation_snapshot()
    assert snap is not None
    assert snap.total_proposals == 0


# 33. Configuration Disabled Behavior
def test_33_config_disabled_behavior() -> None:
    config = ConfigurationManager()
    config.set("autonomy.adaptation_enabled", False)
    engine = RuntimeAdaptivePolicyEngine(config=config)

    try:
        engine.propose_adaptation(
            action_id="act-disabled",
            adaptation_type=AdaptationType.REDUCE_FREQUENCY,
            proposed_value=30,
            reason="Disabled test",
        )
        raise AssertionError("Expected RuntimeError when adaptation engine is disabled")
    except RuntimeError:
        pass


# 34. Stage 13 Recommendation Integration
def test_34_stage13_recommendation_integration() -> None:
    exp_engine = RuntimeExperienceEngine()
    adapt_engine = RuntimeAdaptivePolicyEngine(experience_engine=exp_engine)

    rec = ExperienceRecommendation(
        action_id="act-st13-st14",
        recommendation_type=RecommendationType.REDUCE_FREQUENCY,
        confidence=ExperienceConfidence.HIGH,
        reason="High failure rate",
        supporting_execution_count=12,
        generated_at="2026-08-19T00:00:00Z",
    )

    prop = adapt_engine.create_proposal_from_recommendation(rec)
    assert prop is not None
    assert prop.action_id == "act-st13-st14"
    assert prop.source_recommendation == RecommendationType.REDUCE_FREQUENCY.value


# 35. Stage 11 Compatibility
def test_35_stage11_compatibility() -> None:
    clock = TestClock("2026-08-19T00:00:00Z")
    policy = RuntimePolicyEngine(clock=clock)
    adapt_engine = RuntimeAdaptivePolicyEngine(clock=clock, policy_engine=policy)

    # Adaptation proposals leave Policy Engine evaluation clean
    snap = policy.get_policy_snapshot()
    assert snap is not None

    adapt_engine.propose_adaptation(
        action_id="act-st11",
        adaptation_type=AdaptationType.CHANGE_PRIORITY,
        proposed_value="HIGH",
        reason="Stage 11 compatibility test",
    )

    assert policy.get_policy_snapshot().total_evaluations == snap.total_evaluations


# 36. Stage 10 Governance Compatibility
def test_36_stage10_governance_compatibility() -> None:
    bus = EventBus()
    governance = RuntimeGovernanceEngine(event_bus=bus)
    adapt_engine = RuntimeAdaptivePolicyEngine(event_bus=bus, governance_engine=governance)

    governance.set_authority_scope(AutonomyScope.READ_ONLY)
    assert governance.get_governance_snapshot().scope == AutonomyScope.READ_ONLY

    adapt_engine.propose_adaptation(
        action_id="act-st10",
        adaptation_type=AdaptationType.DISABLE_ACTION,
        proposed_value="DISABLE",
        reason="Stage 10 compatibility test",
    )

    # Governance scope remains READ_ONLY!
    assert governance.get_governance_snapshot().scope == AutonomyScope.READ_ONLY


# 37. Stage 12 Execution Compatibility
def test_37_stage12_execution_compatibility() -> None:
    clock = TestClock("2026-08-19T00:00:00Z")
    execution = RuntimeExecutionEngine(clock=clock)
    adapt_engine = RuntimeAdaptivePolicyEngine(clock=clock)

    action = RuntimeAction("act-st12-st14", "TestStage14Action", execute_fn=lambda ctx: "ok")
    # Adaptation proposals do not invoke ExecutionEngine!
    snap = execution.get_execution_snapshot()
    assert snap.total_executions == 0

    adapt_engine.propose_adaptation(
        action_id=action.action_id,
        adaptation_type=AdaptationType.REDUCE_FREQUENCY,
        proposed_value=30,
        reason="Stage 12 compatibility test",
    )

    assert execution.get_execution_snapshot().total_executions == 0


# 38. Stage 1-9 Compatibility
def test_38_stage1_9_compatibility() -> None:
    clock = TestClock("2026-08-19T00:00:00Z")
    engine = RuntimeAdaptivePolicyEngine(clock=clock)
    snap = engine.get_adaptation_snapshot()
    assert snap is not None
    assert snap.total_proposals == 0


# 39. Full Pipeline Integration
def test_39_full_pipeline_integration() -> None:
    clock = TestClock("2026-08-19T00:00:00Z")
    bus = EventBus()
    experience = RuntimeExperienceEngine(clock=clock, event_bus=bus)
    governance = RuntimeGovernanceEngine(clock=clock, event_bus=bus)
    policy = RuntimePolicyEngine(clock=clock, event_bus=bus)

    adaptation = RuntimeAdaptivePolicyEngine(
        clock=clock,
        event_bus=bus,
        experience_engine=experience,
        governance_engine=governance,
        policy_engine=policy,
    )

    rec = ExperienceRecommendation(
        action_id="act-pipeline",
        recommendation_type=RecommendationType.REDUCE_FREQUENCY,
        confidence=ExperienceConfidence.HIGH,
        reason="Pipeline integration test",
        supporting_execution_count=8,
        generated_at=clock.now_iso(),
    )

    prop = adaptation.create_proposal_from_recommendation(rec)
    assert prop is not None
    assert prop.status == AdaptationStatus.PENDING_APPROVAL

    adaptation.approve_proposal(prop.proposal_id, operator_id="admin_op", reason="Approved")
    app_prop = adaptation.apply_adaptation(prop.proposal_id)
    assert app_prop.status == AdaptationStatus.APPLIED


# 40. Audit Trail Integrity
def test_40_audit_trail_integrity() -> None:
    mem_store = SQLiteMemoryStore(db_path=":memory:")
    adapt_store = RuntimeAdaptationStore(store=mem_store)
    engine = RuntimeAdaptivePolicyEngine(store=adapt_store)

    prop = engine.propose_adaptation(
        action_id="act-audit",
        adaptation_type=AdaptationType.REQUIRE_OPERATOR_REVIEW,
        proposed_value="VAL",
        reason="Audit trail test",
    )
    engine.approve_proposal(prop.proposal_id, operator_id="auditor_op", reason="Audit approval")

    # Verify decision table entry created
    conn = mem_store._get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT operator_id, decision, reason
        FROM runtime_operator_decisions WHERE proposal_id = ?;
        """,
        (prop.proposal_id,),
    )
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == "auditor_op"
    assert row[1] == "APPROVE"
    assert row[2] == "Audit approval"
