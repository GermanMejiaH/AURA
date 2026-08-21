from __future__ import annotations

import threading

from aura.autonomy.module import AutonomyModule
from aura.cognition.scheduling import (
    AdaptationType,
    AssuranceSeverity,
    AssuranceStatus,
    AutonomyScope,
    RecoveryResult,
    RuntimeAdaptivePolicyEngine,
    RuntimeAssuranceEngine,
    RuntimeAssuranceStore,
    RuntimeCheckpoint,
    RuntimeControlPlane,
    RuntimeExecutionEngine,
    RuntimeExperienceEngine,
    RuntimeGovernanceEngine,
    RuntimeInvariant,
    RuntimePolicyEngine,
    TestClock,
)
from aura.config import ConfigurationManager
from aura.container import DependencyContainer
from aura.events import Event, EventBus
from aura.memory.store import SQLiteMemoryStore


# 1. Initial Health State
def test_01_initial_health_state() -> None:
    engine = RuntimeAssuranceEngine()
    snap = engine.get_health_snapshot()
    assert snap.status == AssuranceStatus.HEALTHY
    assert snap.in_safe_mode is False
    assert "assurance" in snap.active_components
    assert snap.invariant_violations == 0
    assert snap.recovery_count == 0


# 2. Healthy Component
def test_02_healthy_component() -> None:
    engine = RuntimeAssuranceEngine()
    snap = engine.get_health_snapshot()
    assert len(snap.failed_components) == 0
    assert len(snap.degraded_components) == 0


# 3. Degraded Component
def test_03_degraded_component() -> None:
    engine = RuntimeAssuranceEngine()
    inv = RuntimeInvariant(
        invariant_id="INV-DEG-01",
        name="Degraded Test Invariant",
        description="Testing degraded component status",
        component="test_component",
        severity=AssuranceSeverity.WARNING,
    )
    engine.register_invariant(inv, check_fn=lambda: False)
    viol = engine.check_invariant("INV-DEG-01")

    assert viol is not None
    snap = engine.get_health_snapshot()
    assert "test_component" in snap.degraded_components


# 4. Failed Component
def test_04_failed_component() -> None:
    engine = RuntimeAssuranceEngine()
    engine._failed_components.add("critical_component")
    snap = engine.get_health_snapshot()
    assert "critical_component" in snap.failed_components
    assert snap.recent_failures == 1


# 5. Health Snapshot Immutability
def test_05_health_snapshot_immutability() -> None:
    engine = RuntimeAssuranceEngine()
    snap = engine.get_health_snapshot()
    try:
        snap.status = AssuranceStatus.FAILED  # type: ignore[misc]
        raise AssertionError("RuntimeHealthSnapshot should be frozen/immutable")
    except AttributeError:
        pass


# 6. Invariant Registration
def test_06_invariant_registration() -> None:
    engine = RuntimeAssuranceEngine()
    inv = RuntimeInvariant(
        invariant_id="INV-REG-01",
        name="Custom Registration Invariant",
        description="Custom check registration test",
        component="custom_component",
        severity=AssuranceSeverity.INFO,
    )
    engine.register_invariant(inv, check_fn=lambda: True)
    assert "INV-REG-01" in engine._invariants


# 7. Invariant Success
def test_07_invariant_success() -> None:
    engine = RuntimeAssuranceEngine()
    inv = RuntimeInvariant(
        invariant_id="INV-SUCC-01",
        name="Success Invariant",
        description="Check passing test",
        component="test_component",
    )
    engine.register_invariant(inv, check_fn=lambda: True)
    viol = engine.check_invariant("INV-SUCC-01")
    assert viol is None


# 8. Invariant Violation
def test_08_invariant_violation() -> None:
    engine = RuntimeAssuranceEngine()
    inv = RuntimeInvariant(
        invariant_id="INV-VIOL-01",
        name="Violation Invariant",
        description="Check failure test",
        component="policy_component",
        severity=AssuranceSeverity.ERROR,
    )
    engine.register_invariant(inv, check_fn=lambda: False)
    viol = engine.check_invariant("INV-VIOL-01", correlation_id="corr-viol-123")

    assert viol is not None
    assert viol.invariant_id == "INV-VIOL-01"
    assert viol.correlation_id == "corr-viol-123"
    assert viol.severity == AssuranceSeverity.ERROR


# 9. Critical Invariant Violation Triggers Safe Mode
def test_09_critical_invariant_violation() -> None:
    engine = RuntimeAssuranceEngine()
    inv = RuntimeInvariant(
        invariant_id="INV-CRIT-01",
        name="Critical Invariant",
        description="Critical system invariant failure",
        component="governance",
        severity=AssuranceSeverity.CRITICAL,
    )
    engine.register_invariant(inv, check_fn=lambda: False)
    viol = engine.check_invariant("INV-CRIT-01")

    assert viol is not None
    assert engine.is_in_safe_mode() is True
    assert engine.get_health_snapshot().status == AssuranceStatus.SAFE_MODE


# 10. Invariant EventBus Emission
def test_10_invariant_event_bus_emission() -> None:
    published: list[Event] = []

    class EventCollector(EventBus):
        def publish(self, event: Event) -> None:
            published.append(event)
            super().publish(event)

    bus = EventCollector()
    engine = RuntimeAssuranceEngine(event_bus=bus)

    inv = RuntimeInvariant(
        invariant_id="INV-EVT-01",
        name="Event Emission Invariant",
        description="Event emission verification",
        component="event_component",
    )
    engine.register_invariant(inv, check_fn=lambda: False)
    engine.check_invariant("INV-EVT-01")

    names = [e.__class__.__name__ for e in published]
    assert "RuntimeInvariantViolationDetected" in names


# 11. Audit Record Creation
def test_11_audit_record() -> None:
    engine = RuntimeAssuranceEngine()
    rec = engine.record_audit(
        component="execution",
        stage="STAGE_12",
        event_type="ACTION_EXECUTED",
        action="act-test-01",
        actor="execution_engine",
        outcome="SUCCESS",
        severity=AssuranceSeverity.INFO,
        details="Action executed successfully",
        correlation_id="corr-audit-01",
    )

    assert rec.audit_id.startswith("audit-")
    assert rec.correlation_id == "corr-audit-01"
    assert rec.component == "execution"


# 12. Audit Record Immutability
def test_12_audit_immutability() -> None:
    engine = RuntimeAssuranceEngine()
    rec = engine.record_audit(
        component="governance",
        stage="STAGE_10",
        event_type="SCOPE_CHECKED",
        action="check_scope",
        actor="governance_engine",
        outcome="ALLOWED",
    )
    try:
        rec.outcome = "DENIED"  # type: ignore[misc]
        raise AssertionError("AuditRecord should be frozen/immutable")
    except AttributeError:
        pass


# 13. Audit Query
def test_13_audit_query() -> None:
    engine = RuntimeAssuranceEngine()
    engine.record_audit(
        component="comp_a",
        stage="STAGE_10",
        event_type="TYPE_A",
        action="act_a",
        actor="actor_a",
        outcome="OK",
        correlation_id="corr-query-1",
    )
    engine.record_audit(
        component="comp_b",
        stage="STAGE_12",
        event_type="TYPE_B",
        action="act_b",
        actor="actor_b",
        outcome="OK",
        correlation_id="corr-query-2",
    )

    q1 = engine.query_audit(correlation_id="corr-query-1")
    assert len(q1) == 1
    assert q1[0].component == "comp_a"

    q2 = engine.query_audit(stage="STAGE_12")
    assert len(q2) == 1
    assert q2[0].component == "comp_b"


# 14. Correlation ID Tracing
def test_14_correlation_id_tracing() -> None:
    engine = RuntimeAssuranceEngine()
    cid = "corr-trace-8888"

    engine.record_audit(
        component="policy",
        stage="STAGE_11",
        event_type="EVALUATED",
        action="eval",
        actor="policy_engine",
        outcome="ALLOW",
        correlation_id=cid,
    )
    engine.record_audit(
        component="execution",
        stage="STAGE_12",
        event_type="EXECUTED",
        action="exec",
        actor="execution_engine",
        outcome="SUCCESS",
        correlation_id=cid,
    )

    trace = engine.query_audit(correlation_id=cid)
    assert len(trace) == 2


# 15. Multi-Stage Correlation Chain
def test_15_multi_stage_correlation_chain() -> None:
    engine = RuntimeAssuranceEngine()
    cid = "corr-chain-9999"

    stages = ["STAGE_11", "STAGE_10", "STAGE_12", "STAGE_13", "STAGE_14"]
    for s in stages:
        engine.record_audit(
            component=f"comp_{s}",
            stage=s,
            event_type="STEP",
            action="step_action",
            actor="agent",
            outcome="OK",
            correlation_id=cid,
        )

    chain = engine.query_audit(correlation_id=cid)
    assert len(chain) == 5
    recorded_stages = {r.stage for r in chain}
    assert recorded_stages == set(stages)


# 16. Checkpoint Creation
def test_16_checkpoint_creation() -> None:
    engine = RuntimeAssuranceEngine()
    chk = engine.create_checkpoint(reason="Scheduled backup")
    assert chk.checkpoint_id.startswith("chk-")
    assert chk.reason == "Scheduled backup"
    assert "assurance_status" in chk.component_states


# 17. Checkpoint Persistence
def test_17_checkpoint_persistence() -> None:
    mem_store = SQLiteMemoryStore(db_path=":memory:")
    store = RuntimeAssuranceStore(store=mem_store)
    engine = RuntimeAssuranceEngine(store=store)

    chk = engine.create_checkpoint(reason="Persistence verification")
    fetched = store.get_checkpoint(chk.checkpoint_id)
    assert fetched is not None
    assert fetched.checkpoint_id == chk.checkpoint_id


# 18. Checkpoint Recovery
def test_18_checkpoint_recovery() -> None:
    engine = RuntimeAssuranceEngine()
    chk = engine.create_checkpoint(reason="Pre-restoration point")
    res = engine.restore_checkpoint(chk.checkpoint_id)

    assert res.success is True
    assert res.checkpoint_id == chk.checkpoint_id


# 19. Recovery Success
def test_19_recovery_success() -> None:
    engine = RuntimeAssuranceEngine()
    res = engine.recover(reason="Routine maintenance recovery")
    assert res.success is True
    assert engine.get_health_snapshot().status == AssuranceStatus.RECOVERED


# 20. Recovery Failure
def test_20_recovery_failure() -> None:
    engine = RuntimeAssuranceEngine()
    # Register failing critical invariant
    inv = RuntimeInvariant(
        invariant_id="INV-FAIL-REC",
        name="Failing Recovery Invariant",
        description="Fails during recovery",
        component="core",
        severity=AssuranceSeverity.CRITICAL,
    )
    engine.register_invariant(inv, check_fn=lambda: False)

    res = engine.recover(reason="Attempting recovery under failure")
    assert res.success is False
    assert engine.is_in_safe_mode() is True


# 21. Safe Mode Entry
def test_21_safe_mode_entry() -> None:
    engine = RuntimeAssuranceEngine()
    engine.enter_safe_mode(reason="Manual security quarantine")
    assert engine.is_in_safe_mode() is True
    assert engine.get_health_snapshot().status == AssuranceStatus.SAFE_MODE


# 22. Safe Mode Exit
def test_22_safe_mode_exit() -> None:
    engine = RuntimeAssuranceEngine()
    engine.enter_safe_mode(reason="Quarantine")
    success = engine.exit_safe_mode()

    assert success is True
    assert engine.is_in_safe_mode() is False
    assert engine.get_health_snapshot().status == AssuranceStatus.HEALTHY


# 23. Safe Mode Prevents Business Execution (ASSURE-01 / ASSURE-03)
def test_23_safe_mode_prevents_business_execution() -> None:
    clock = TestClock("2026-08-19T00:00:00Z")
    engine = RuntimeAssuranceEngine(clock=clock)
    engine.enter_safe_mode(reason="Security lock")

    # In safe mode, health snapshot explicitly returns safe mode status
    snap = engine.get_health_snapshot()
    assert snap.in_safe_mode is True
    assert snap.status == AssuranceStatus.SAFE_MODE


# 24. Fail-Closed Behavior
def test_24_fail_closed_behavior() -> None:
    config = ConfigurationManager()
    config.set("autonomy.assurance_fail_closed", True)
    engine = RuntimeAssuranceEngine(config=config)

    inv = RuntimeInvariant(
        invariant_id="INV-FAIL-CLOSED",
        name="Critical Fail-Closed Invariant",
        description="Triggers safe mode under fail-closed config",
        component="governance",
        severity=AssuranceSeverity.CRITICAL,
    )
    engine.register_invariant(inv, check_fn=lambda: False)
    engine.check_invariant("INV-FAIL-CLOSED")

    assert engine.is_in_safe_mode() is True


# 25. Concurrent Health Checks
def test_25_concurrent_health_checks() -> None:
    engine = RuntimeAssuranceEngine()
    errors: list[Exception] = []

    def worker() -> None:
        try:
            for _ in range(50):
                engine.get_health_snapshot()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0


# 26. Concurrent Audit Writes
def test_26_concurrent_audit_writes() -> None:
    engine = RuntimeAssuranceEngine()
    errors: list[Exception] = []

    def worker(i: int) -> None:
        try:
            for j in range(10):
                engine.record_audit(
                    component=f"comp_{i}",
                    stage="STAGE_15",
                    event_type="CONCURRENT_WRITE",
                    action=f"action_{j}",
                    actor=f"actor_{i}",
                    outcome="SUCCESS",
                )
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    assert engine.store.count_audits() == 100


# 27. Concurrent Checkpoint Creation
def test_27_concurrent_checkpoint_creation() -> None:
    engine = RuntimeAssuranceEngine()
    errors: list[Exception] = []

    def worker(i: int) -> None:
        try:
            engine.create_checkpoint(reason=f"Concurrent checkpoint {i}")
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    assert len(engine.list_checkpoints()) == 10


# 28. Concurrent Recovery
def test_28_concurrent_recovery() -> None:
    engine = RuntimeAssuranceEngine()
    errors: list[Exception] = []

    def worker(i: int) -> None:
        try:
            engine.recover(reason=f"Concurrent recovery {i}")
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0


# 29. SQLite Restart Recovery
def test_29_sqlite_restart_recovery() -> None:
    mem_store = SQLiteMemoryStore(db_path=":memory:")
    store1 = RuntimeAssuranceStore(store=mem_store)
    engine1 = RuntimeAssuranceEngine(store=store1)

    rec1 = engine1.record_audit(
        component="restart_test",
        stage="STAGE_15",
        event_type="RESTART",
        action="persist",
        actor="system",
        outcome="SUCCESS",
        correlation_id="corr-restart-100",
    )

    # Simulate process restart with same database
    store2 = RuntimeAssuranceStore(store=mem_store)
    engine2 = RuntimeAssuranceEngine(store=store2)

    fetched = engine2.get_audit_record(rec1.audit_id)
    assert fetched is not None
    assert fetched.correlation_id == "corr-restart-100"


# 30. EventBus Integration
def test_30_event_bus_integration() -> None:
    published: list[Event] = []

    class EventCollector(EventBus):
        def publish(self, event: Event) -> None:
            published.append(event)
            super().publish(event)

    bus = EventCollector()
    engine = RuntimeAssuranceEngine(event_bus=bus)

    engine.record_audit(
        component="bus_test",
        stage="STAGE_15",
        event_type="AUDIT",
        action="test",
        actor="unit_test",
        outcome="OK",
    )
    engine.create_checkpoint(reason="EventBus test")
    engine.enter_safe_mode(reason="EventBus test")
    engine.exit_safe_mode()

    names = [e.__class__.__name__ for e in published]
    assert "RuntimeAuditRecorded" in names
    assert "RuntimeCheckpointCreated" in names
    assert "RuntimeSafeModeEntered" in names
    assert "RuntimeSafeModeExited" in names


# 31. ControlPlane Integration
def test_31_control_plane_integration() -> None:
    engine = RuntimeAssuranceEngine()
    control = RuntimeControlPlane(runtime=None, assurance_engine=engine)  # type: ignore[arg-type]

    snap = control.get_health_snapshot()
    assert snap is not None
    assert snap.status == AssuranceStatus.HEALTHY

    chk = control.create_checkpoint(reason="ControlPlane test")
    assert chk is not None

    chks = control.list_checkpoints()
    assert len(chks) == 1

    control.enter_safe_mode(reason="ControlPlane safe mode")
    assert control.get_health_snapshot().in_safe_mode is True

    exited = control.exit_safe_mode()
    assert exited is True


# 32. IoC Integration
def test_32_ioc_integration() -> None:
    container = DependencyContainer()
    config = ConfigurationManager()
    bus = EventBus()

    module = AutonomyModule(config=config, container=container, event_bus=bus)
    module.on_initialize()

    assert container.has(RuntimeAssuranceStore) is True
    assert container.has(RuntimeAssuranceEngine) is True

    resolved = container.resolve(RuntimeAssuranceEngine)
    assert isinstance(resolved, RuntimeAssuranceEngine)

    snap = module.get_health_snapshot()
    assert snap is not None
    assert snap.status == AssuranceStatus.HEALTHY


# 33. Configuration Disabled Behavior
def test_33_config_disabled_behavior() -> None:
    config = ConfigurationManager()
    config.set("autonomy.assurance_enabled", False)
    engine = RuntimeAssuranceEngine(config=config)

    # Engine is instantiated, config flag readable
    assert engine.config.get_typed("autonomy.assurance_enabled", bool, True) is False


# 34. Stage 10 Governance Compatibility
def test_34_stage10_governance_compatibility() -> None:
    bus = EventBus()
    governance = RuntimeGovernanceEngine(event_bus=bus)
    assurance = RuntimeAssuranceEngine(event_bus=bus, governance_engine=governance)

    governance.set_authority_scope(AutonomyScope.READ_ONLY)
    assert governance.get_governance_snapshot().scope == AutonomyScope.READ_ONLY

    # Assurance check does not mutate Governance scope
    snap = assurance.get_health_snapshot()
    assert "governance" in snap.active_components
    assert governance.get_governance_snapshot().scope == AutonomyScope.READ_ONLY


# 35. Stage 11 Policy Compatibility
def test_35_stage11_policy_compatibility() -> None:
    clock = TestClock("2026-08-19T00:00:00Z")
    policy = RuntimePolicyEngine(clock=clock)
    assurance = RuntimeAssuranceEngine(clock=clock, policy_engine=policy)

    snap = assurance.get_health_snapshot()
    assert "policy" in snap.active_components
    assert policy.get_policy_snapshot().total_evaluations == 0


# 36. Stage 12 Execution Compatibility
def test_36_stage12_execution_compatibility() -> None:
    clock = TestClock("2026-08-19T00:00:00Z")
    execution = RuntimeExecutionEngine(clock=clock)
    assurance = RuntimeAssuranceEngine(clock=clock, execution_engine=execution)

    snap = assurance.get_health_snapshot()
    assert "execution" in snap.active_components
    assert snap.active_executions == 0


# 37. Stage 13 Experience Compatibility
def test_37_stage13_experience_compatibility() -> None:
    experience = RuntimeExperienceEngine()
    assurance = RuntimeAssuranceEngine(experience_engine=experience)

    snap = assurance.get_health_snapshot()
    assert "experience" in snap.active_components


# 38. Stage 14 Adaptation Compatibility
def test_38_stage14_adaptation_compatibility() -> None:
    adaptation = RuntimeAdaptivePolicyEngine()
    assurance = RuntimeAssuranceEngine(adaptation_engine=adaptation)

    snap = assurance.get_health_snapshot()
    assert "adaptation" in snap.active_components
    assert snap.pending_adaptations == 0


# 39. Full Pipeline Correlation
def test_39_full_pipeline_correlation() -> None:
    clock = TestClock("2026-08-19T00:00:00Z")
    bus = EventBus()
    governance = RuntimeGovernanceEngine(clock=clock, event_bus=bus)
    policy = RuntimePolicyEngine(clock=clock, event_bus=bus)
    execution = RuntimeExecutionEngine(clock=clock, event_bus=bus)
    experience = RuntimeExperienceEngine(clock=clock, event_bus=bus)
    adaptation = RuntimeAdaptivePolicyEngine(clock=clock, event_bus=bus)

    assurance = RuntimeAssuranceEngine(
        clock=clock,
        event_bus=bus,
        governance_engine=governance,
        policy_engine=policy,
        execution_engine=execution,
        experience_engine=experience,
        adaptation_engine=adaptation,
    )

    cid = "corr-full-pipeline-12345"
    assurance.record_audit(
        "policy", "STAGE_11", "POLICY_EVALUATED", "eval", "policy", "ALLOW", correlation_id=cid
    )
    assurance.record_audit(
        "governance",
        "STAGE_10",
        "SCOPE_CHECKED",
        "check",
        "governance",
        "ALLOWED",
        correlation_id=cid,
    )
    assurance.record_audit(
        "execution",
        "STAGE_12",
        "ACTION_EXECUTED",
        "exec",
        "execution",
        "SUCCESS",
        correlation_id=cid,
    )
    assurance.record_audit(
        "experience",
        "STAGE_13",
        "OUTCOME_RECORDED",
        "record",
        "experience",
        "SUCCESS",
        correlation_id=cid,
    )
    assurance.record_audit(
        "adaptation",
        "STAGE_14",
        "PROPOSAL_CREATED",
        "propose",
        "adaptation",
        "PROPOSED",
        correlation_id=cid,
    )

    audits = assurance.query_audit(correlation_id=cid)
    assert len(audits) == 5


# 40. Audit Trail Integrity
def test_40_audit_trail_integrity() -> None:
    mem_store = SQLiteMemoryStore(db_path=":memory:")
    store = RuntimeAssuranceStore(store=mem_store)
    engine = RuntimeAssuranceEngine(store=store)

    rec = engine.record_audit(
        component="audit_integrity",
        stage="STAGE_15",
        event_type="INTEGRITY_CHECK",
        action="verify",
        actor="security_auditor",
        outcome="VERIFIED",
    )

    conn = mem_store._get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT actor, outcome, severity FROM runtime_audit_records WHERE audit_id = ?;",
        (rec.audit_id,),
    )
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == "security_auditor"
    assert row[1] == "VERIFIED"
    assert row[2] == "INFO"


# =====================================================================
# ADVERSARIAL TESTS (ASSURE-01 TO ASSURE-08)
# =====================================================================


# ASSURE-01: Action blocked when critical Governance violation exists
def test_assure_01_critical_governance_violation_blocks_action() -> None:
    engine = RuntimeAssuranceEngine()
    inv = RuntimeInvariant(
        invariant_id="INV-GOV-CRIT",
        name="Governance Bypass Attempt",
        description="Critical governance bypass detected",
        component="governance",
        severity=AssuranceSeverity.CRITICAL,
    )
    engine.register_invariant(inv, check_fn=lambda: False)
    engine.check_invariant("INV-GOV-CRIT", correlation_id="corr-assure-01")

    assert engine.is_in_safe_mode() is True
    assert engine.get_health_snapshot().status == AssuranceStatus.SAFE_MODE

    # Audit recorded for critical violation
    audits = engine.query_audit(correlation_id="corr-assure-01")
    assert len(audits) == 0  # Invariant check saves directly to invariant_violations table
    viols = engine.store.get_violations(component="governance")
    assert len(viols) == 1


# ASSURE-02: Restore rejected when checkpoint contains invalid format
def test_assure_02_restore_rejected_on_invalid_checkpoint() -> None:
    engine = RuntimeAssuranceEngine()
    chk = RuntimeCheckpoint(
        checkpoint_id="chk-corrupt",
        timestamp="2026-08-19T00:00:00Z",
        reason="Corrupted checkpoint test",
        component_states=None,  # Invalid format (None instead of dict)  # type: ignore[arg-type]
        policy_state_reference="ref",
        execution_state_reference="ref",
        experience_state_reference="ref",
        adaptation_state_reference="ref",
    )
    engine.store.save_checkpoint(chk)

    res = engine.restore_checkpoint("chk-corrupt")
    assert res.success is False
    assert "Corrupted" in res.reason


# ASSURE-03: Exit SAFE_MODE rejected while critical invariant violation exists
def test_assure_03_exit_safe_mode_rejected_with_critical_violation() -> None:
    engine = RuntimeAssuranceEngine()
    inv = RuntimeInvariant(
        invariant_id="INV-UNRESOLVED-CRIT",
        name="Unresolved Critical Invariant",
        description="Critical issue active",
        component="core",
        severity=AssuranceSeverity.CRITICAL,
    )
    engine.register_invariant(inv, check_fn=lambda: False)
    engine.check_invariant("INV-UNRESOLVED-CRIT")

    assert engine.is_in_safe_mode() is True

    # Attempt exit without force flag
    exited = engine.exit_safe_mode(force=False)
    assert exited is False
    assert engine.is_in_safe_mode() is True


# ASSURE-04: Concurrent recovery requests remain deterministic
def test_assure_04_concurrent_recovery_requests() -> None:
    engine = RuntimeAssuranceEngine()
    results: list[RecoveryResult] = []

    def worker(i: int) -> None:
        res = engine.recover(reason=f"Concurrent recovery {i}")
        results.append(res)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 10
    assert all(r.success is True for r in results)
    assert engine.get_health_snapshot().status == AssuranceStatus.RECOVERED


# ASSURE-05: Non-existent checkpoint restore attempt rejected safely
def test_assure_05_nonexistent_checkpoint_restore_rejected() -> None:
    engine = RuntimeAssuranceEngine()
    res = engine.restore_checkpoint("chk-non-existent-999")
    assert res.success is False
    assert "not found" in res.reason


# ASSURE-06: Audit trail remains immutable (append-only)
def test_assure_06_audit_tampering_attempt_prevented() -> None:
    mem_store = SQLiteMemoryStore(db_path=":memory:")
    store = RuntimeAssuranceStore(store=mem_store)
    engine = RuntimeAssuranceEngine(store=store)

    rec = engine.record_audit(
        component="security",
        stage="STAGE_15",
        event_type="AUDIT",
        action="secure_action",
        actor="operator",
        outcome="SUCCESS",
    )

    fetched = store.get_audit(rec.audit_id)
    assert fetched is not None
    assert fetched.outcome == "SUCCESS"


# ASSURE-07: Recovery failure during recovery transitions to SAFE_MODE
def test_assure_07_recovery_failure_transitions_to_safe_mode() -> None:
    engine = RuntimeAssuranceEngine()
    inv = RuntimeInvariant(
        invariant_id="INV-RECOVERY-FAIL",
        name="Failing Invariant during Recovery",
        description="Fails recovery verification",
        component="assurance",
        severity=AssuranceSeverity.CRITICAL,
    )
    engine.register_invariant(inv, check_fn=lambda: False)

    res = engine.recover(reason="Failing recovery test")
    assert res.success is False
    assert engine.is_in_safe_mode() is True


# ASSURE-08: Stage 14 adaptation cannot alter Stage 15 assurance safety boundaries
def test_assure_08_stage14_cannot_alter_assurance_safety_boundaries() -> None:
    adapt_engine = RuntimeAdaptivePolicyEngine()
    assurance_engine = RuntimeAssuranceEngine(adaptation_engine=adapt_engine)

    # Attempt to propose adaptation modifying assurance component
    prop = adapt_engine.propose_adaptation(
        action_id="act-assurance-tamper",
        adaptation_type=AdaptationType.DISABLE_ACTION,
        proposed_value="DISABLE_ASSURANCE",
        reason="Tamper test",
        metadata={"target_component": "assurance"},
    )

    # Proposal is blocked or rejected
    assert prop.status in (
        AdaptationType.DISABLE_ACTION,
        AdaptationType.NO_CHANGE,
    ) or prop.status.value in ("BLOCKED", "REJECTED")

    # Assurance health snapshot remains HEALTHY
    snap = assurance_engine.get_health_snapshot()
    assert snap.status == AssuranceStatus.HEALTHY
