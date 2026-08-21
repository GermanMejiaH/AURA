from __future__ import annotations

import threading

from aura.autonomy.module import AutonomyModule
from aura.cognition.goals import GoalManager as CognitionGoalManager
from aura.cognition.goals import GoalStore
from aura.cognition.scheduling import (
    AutonomyScope,
    ExecutionContext,
    ExperienceConfidence,
    ExperienceStatusSnapshot,
    OutcomeRecord,
    OutcomeType,
    RecommendationType,
    RuntimeAction,
    RuntimeControlPlane,
    RuntimeExecutionEngine,
    RuntimeExperienceEngine,
    RuntimeExperienceStore,
    RuntimeGovernanceEngine,
    RuntimePolicyEngine,
    ScheduleDispatcher,
    ScheduleStore,
    ScheduleType,
    TemporalSchedule,
    TestClock,
)
from aura.config import ConfigurationManager
from aura.container import DependencyContainer
from aura.events import (
    Event,
    EventBus,
    RuntimeExecutionCompleted,
)
from aura.memory.store import SQLiteMemoryStore


def create_test_schedule(
    goal_mgr: CognitionGoalManager,
    schedule_id: str = "sched-exp-001",
) -> TemporalSchedule:
    g = goal_mgr.create_goal(description="Test experience goal")
    return TemporalSchedule(
        schedule_id=schedule_id,
        goal_id=g.goal_id,
        schedule_type=ScheduleType.CRON,
        expression="* * * * *",
    )


# 1. Initial Experience State
def test_01_initial_experience_state() -> None:
    engine = RuntimeExperienceEngine()
    snap = engine.get_experience_snapshot()
    assert snap.total_outcomes == 0
    assert snap.tracked_actions == 0
    assert snap.recommendations_generated == 0
    assert snap.failure_patterns_detected == 0


# 2. Immutable OutcomeRecord
def test_02_immutable_outcome_record() -> None:
    rec = OutcomeRecord(
        execution_id="exec-01",
        action_id="act-01",
        outcome_type=OutcomeType.SUCCESS,
        success=True,
    )
    assert rec.execution_id == "exec-01"
    assert rec.action_id == "act-01"
    assert rec.success is True
    try:
        rec.success = False  # type: ignore[misc]
        raise AssertionError("OutcomeRecord should be frozen/immutable")
    except AttributeError:
        pass


# 3. Record Successful Outcome
def test_03_record_successful_outcome() -> None:
    engine = RuntimeExperienceEngine()
    rec = OutcomeRecord(
        execution_id="exec-succ",
        action_id="act-succ",
        outcome_type=OutcomeType.SUCCESS,
        success=True,
        started_at="2026-08-19T00:00:00Z",
        completed_at="2026-08-19T00:00:01Z",
        duration_seconds=1.0,
    )
    engine.record_outcome(rec)
    assert engine.store.count() == 1
    stored = engine.store.get_outcome("exec-succ")
    assert stored is not None
    assert stored.success is True


# 4. Record Failed Outcome
def test_04_record_failed_outcome() -> None:
    engine = RuntimeExperienceEngine()
    rec = OutcomeRecord(
        execution_id="exec-fail",
        action_id="act-fail",
        outcome_type=OutcomeType.FAILURE,
        success=False,
        failure_type="PERMANENT",
        error="Resource unavailable",
    )
    engine.record_outcome(rec)
    exp = engine.get_action_experience("act-fail")
    assert exp.failed_executions == 1
    assert exp.last_failure_type == "PERMANENT"


# 5. Record Timeout Outcome
def test_05_record_timeout_outcome() -> None:
    engine = RuntimeExperienceEngine()
    rec = OutcomeRecord(
        execution_id="exec-to",
        action_id="act-to",
        outcome_type=OutcomeType.TIMED_OUT,
        success=False,
        error="Timeout after 30s",
    )
    engine.record_outcome(rec)
    exp = engine.get_action_experience("act-to")
    assert exp.timeout_executions == 1
    assert exp.consecutive_failures == 1


# 6. Record Rollback Outcome
def test_06_record_rollback_outcome() -> None:
    engine = RuntimeExperienceEngine()
    rec = OutcomeRecord(
        execution_id="exec-rb",
        action_id="act-rb",
        outcome_type=OutcomeType.ROLLED_BACK,
        success=False,
        rollback_performed=True,
    )
    engine.record_outcome(rec)
    exp = engine.get_action_experience("act-rb")
    assert exp.rollback_executions == 1


# 7. Record Compensation Outcome
def test_07_record_compensation_outcome() -> None:
    engine = RuntimeExperienceEngine()
    rec = OutcomeRecord(
        execution_id="exec-comp",
        action_id="act-comp",
        outcome_type=OutcomeType.COMPENSATED,
        success=True,
        compensation_performed=True,
    )
    engine.record_outcome(rec)
    exp = engine.get_action_experience("act-comp")
    assert exp.compensation_executions == 1


# 8. Action Experience Aggregation
def test_08_action_experience_aggregation() -> None:
    engine = RuntimeExperienceEngine()
    for i in range(5):
        rec = OutcomeRecord(
            execution_id=f"e-{i}",
            action_id="act-agg",
            outcome_type=OutcomeType.SUCCESS if i < 4 else OutcomeType.FAILURE,
            success=(i < 4),
            duration_seconds=2.0,
        )
        engine.record_outcome(rec)

    exp = engine.get_action_experience("act-agg")
    assert exp.total_executions == 5
    assert exp.successful_executions == 4
    assert exp.failed_executions == 1
    assert exp.average_duration_seconds == 2.0


# 9. Success Rate Calculation
def test_09_success_rate_calculation() -> None:
    engine = RuntimeExperienceEngine()
    for i in range(10):
        rec = OutcomeRecord(
            execution_id=f"e-s-{i}",
            action_id="act-rate",
            outcome_type=OutcomeType.SUCCESS if i < 8 else OutcomeType.FAILURE,
            success=(i < 8),
        )
        engine.record_outcome(rec)

    exp = engine.get_action_experience("act-rate")
    assert exp.success_rate == 0.80
    assert exp.failure_rate == 0.20


# 10. Failure Rate Calculation
def test_10_failure_rate_calculation() -> None:
    engine = RuntimeExperienceEngine()
    for i in range(4):
        rec = OutcomeRecord(
            execution_id=f"e-f-{i}",
            action_id="act-frate",
            outcome_type=OutcomeType.FAILURE,
            success=False,
        )
        engine.record_outcome(rec)

    exp = engine.get_action_experience("act-frate")
    assert exp.failure_rate == 1.0
    assert exp.success_rate == 0.0


# 11. Consecutive Failures Tracking
def test_11_consecutive_failures_tracking() -> None:
    engine = RuntimeExperienceEngine()
    # 2 successes then 3 failures
    for i in range(5):
        rec = OutcomeRecord(
            execution_id=f"e-cf-{i}",
            action_id="act-cf",
            outcome_type=OutcomeType.SUCCESS if i < 2 else OutcomeType.FAILURE,
            success=(i < 2),
        )
        engine.record_outcome(rec)

    exp = engine.get_action_experience("act-cf")
    assert exp.consecutive_failures == 3
    assert exp.consecutive_successes == 0


# 12. Consecutive Successes Tracking
def test_12_consecutive_successes_tracking() -> None:
    engine = RuntimeExperienceEngine()
    # 2 failures then 4 successes
    for i in range(6):
        rec = OutcomeRecord(
            execution_id=f"e-cs-{i}",
            action_id="act-cs",
            outcome_type=OutcomeType.FAILURE if i < 2 else OutcomeType.SUCCESS,
            success=(i >= 2),
        )
        engine.record_outcome(rec)

    exp = engine.get_action_experience("act-cs")
    assert exp.consecutive_successes == 4
    assert exp.consecutive_failures == 0


# 13. Repeated Failure Type Detection
def test_13_repeated_failure_type_detection() -> None:
    engine = RuntimeExperienceEngine()
    for i in range(3):
        rec = OutcomeRecord(
            execution_id=f"e-rf-{i}",
            action_id="act-rept",
            outcome_type=OutcomeType.FAILURE,
            success=False,
            failure_type="NETWORK_TIMEOUT",
        )
        engine.record_outcome(rec)

    patterns = engine.get_failure_patterns("act-rept")
    p_types = [p["pattern_type"] for p in patterns]
    assert "REPEATED_FAILURE_TYPE" in p_types


# 14. Timeout Pattern Detection
def test_14_timeout_pattern_detection() -> None:
    engine = RuntimeExperienceEngine()
    for i in range(3):
        rec = OutcomeRecord(
            execution_id=f"e-top-{i}",
            action_id="act-topat",
            outcome_type=OutcomeType.TIMED_OUT,
            success=False,
        )
        engine.record_outcome(rec)

    patterns = engine.get_failure_patterns("act-topat")
    p_types = [p["pattern_type"] for p in patterns]
    assert "TIMEOUT_PATTERN" in p_types


# 15. Rollback Pattern Detection
def test_15_rollback_pattern_detection() -> None:
    engine = RuntimeExperienceEngine()
    for i in range(2):
        rec = OutcomeRecord(
            execution_id=f"e-rbp-{i}",
            action_id="act-rbpat",
            outcome_type=OutcomeType.ROLLED_BACK,
            success=False,
            rollback_performed=True,
        )
        engine.record_outcome(rec)

    patterns = engine.get_failure_patterns("act-rbpat")
    p_types = [p["pattern_type"] for p in patterns]
    assert "ROLLBACK_PATTERN" in p_types


# 16. Compensation Pattern Detection
def test_16_compensation_pattern_detection() -> None:
    engine = RuntimeExperienceEngine()
    rec = OutcomeRecord(
        execution_id="e-cmpp-0",
        action_id="act-cmppat",
        outcome_type=OutcomeType.COMPENSATED,
        success=True,
        compensation_performed=True,
    )
    engine.record_outcome(rec)

    patterns = engine.get_failure_patterns("act-cmppat")
    p_types = [p["pattern_type"] for p in patterns]
    assert "COMPENSATION_PATTERN" in p_types


# 17. Recommendation Generation
def test_17_recommendation_generation() -> None:
    engine = RuntimeExperienceEngine()
    for i in range(5):
        rec = OutcomeRecord(
            execution_id=f"e-rec-{i}",
            action_id="act-good",
            outcome_type=OutcomeType.SUCCESS,
            success=True,
        )
        engine.record_outcome(rec)

    recs = engine.get_recommendations("act-good")
    assert len(recs) == 1
    assert recs[0].recommendation_type == RecommendationType.KEEP_CURRENT_POLICY


# 18. Confidence Calculation
def test_18_confidence_calculation() -> None:
    engine = RuntimeExperienceEngine()
    for i in range(12):
        rec = OutcomeRecord(
            execution_id=f"e-conf-{i}",
            action_id="act-conf",
            outcome_type=OutcomeType.SUCCESS,
            success=True,
        )
        engine.record_outcome(rec)

    exp = engine.get_action_experience("act-conf")
    assert exp.confidence == ExperienceConfidence.HIGH


# 19. Operator Review Recommendation
def test_19_operator_review_recommendation() -> None:
    engine = RuntimeExperienceEngine()
    for i in range(3):
        rec = OutcomeRecord(
            execution_id=f"e-op-{i}",
            action_id="act-bad",
            outcome_type=OutcomeType.FAILURE,
            success=False,
        )
        engine.record_outcome(rec)

    recs = engine.get_recommendations("act-bad")
    assert len(recs) == 1
    assert recs[0].recommendation_type == RecommendationType.REQUIRE_OPERATOR_REVIEW


# 20. Deterministic Recommendations
def test_20_deterministic_recommendations() -> None:
    clock = TestClock("2026-08-19T00:00:00Z")
    engine1 = RuntimeExperienceEngine(clock=clock)
    engine2 = RuntimeExperienceEngine(clock=clock)

    for i in range(4):
        rec = OutcomeRecord(
            execution_id=f"e-det-{i}",
            action_id="act-det",
            outcome_type=OutcomeType.SUCCESS if i < 3 else OutcomeType.FAILURE,
            success=(i < 3),
        )
        engine1.record_outcome(rec)
        engine2.record_outcome(rec)

    r1 = engine1.get_recommendations("act-det")[0]
    r2 = engine2.get_recommendations("act-det")[0]

    assert r1.recommendation_type == r2.recommendation_type
    assert r1.reason == r2.reason


# 21. SQLite Persistence Integration
def test_21_sqlite_persistence() -> None:
    mem_store = SQLiteMemoryStore(db_path=":memory:")
    exp_store = RuntimeExperienceStore(store=mem_store)
    engine = RuntimeExperienceEngine(store=exp_store)

    rec = OutcomeRecord(
        execution_id="exec-sql",
        action_id="act-sql",
        outcome_type=OutcomeType.SUCCESS,
        success=True,
    )
    engine.record_outcome(rec)

    assert exp_store.count() == 1
    stored = exp_store.get_outcome("exec-sql")
    assert stored is not None
    assert stored.action_id == "act-sql"


# 22. Idempotent Outcome Persistence
def test_22_idempotent_outcome_persistence() -> None:
    engine = RuntimeExperienceEngine()
    rec = OutcomeRecord(
        execution_id="exec-idemp",
        action_id="act-idemp",
        outcome_type=OutcomeType.SUCCESS,
        success=True,
    )
    engine.record_outcome(rec)
    engine.record_outcome(rec)  # Duplicate write

    assert engine.store.count() == 1  # Replaced, not duplicated!


# 23. Concurrent Writes Safety
def test_23_concurrent_writes_safety() -> None:
    engine = RuntimeExperienceEngine()
    errors: list[Exception] = []

    def worker(i: int) -> None:
        try:
            rec = OutcomeRecord(
                execution_id=f"e-cw-{i}",
                action_id="act-cw",
                outcome_type=OutcomeType.SUCCESS,
                success=True,
            )
            engine.record_outcome(rec)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    assert engine.store.count("act-cw") == 20


# 24. Concurrent Reads Safety
def test_24_concurrent_reads_safety() -> None:
    engine = RuntimeExperienceEngine()
    rec = OutcomeRecord(
        execution_id="e-cr-0",
        action_id="act-cr",
        outcome_type=OutcomeType.SUCCESS,
        success=True,
    )
    engine.record_outcome(rec)

    errors: list[Exception] = []

    def worker() -> None:
        try:
            exp = engine.get_action_experience("act-cr")
            assert exp.total_executions == 1
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0


# 25. EventBus Integration Emission
def test_25_event_bus_publishing() -> None:
    published: list[Event] = []

    class EventCollector(EventBus):
        def publish(self, event: Event) -> None:
            published.append(event)
            super().publish(event)

    bus = EventCollector()
    engine = RuntimeExperienceEngine(event_bus=bus)

    rec = OutcomeRecord(
        execution_id="e-eb-1",
        action_id="act-eb",
        outcome_type=OutcomeType.SUCCESS,
        success=True,
    )
    engine.record_outcome(rec)

    event_names = [e.__class__.__name__ for e in published]
    assert "RuntimeOutcomeRecorded" in event_names
    assert "RuntimeExperienceUpdated" in event_names
    assert "RuntimeRecommendationGenerated" in event_names


# 26. Stage 12 Event Integration
def test_26_stage12_event_integration() -> None:
    bus = EventBus()
    engine = RuntimeExperienceEngine(event_bus=bus)

    # Publish Stage 12 event directly on EventBus
    bus.publish(
        RuntimeExecutionCompleted(
            execution_id="exec-st12-01",
            goal_id="goal-st12-01",
            state="COMMITTED",
        )
    )

    assert engine.store.count() == 1
    out = engine.store.get_outcome("exec-st12-01")
    assert out is not None
    assert out.success is True


# 27. Control Plane Integration
def test_27_control_plane_integration() -> None:
    engine = RuntimeExperienceEngine()
    control = RuntimeControlPlane(runtime=None, experience_engine=engine)  # type: ignore[arg-type]

    rec = OutcomeRecord(
        execution_id="e-cp-1",
        action_id="act-cp",
        outcome_type=OutcomeType.SUCCESS,
        success=True,
    )
    engine.record_outcome(rec)

    snap = control.get_experience_snapshot()
    assert snap is not None
    assert snap.total_outcomes == 1
    assert len(control.get_recent_outcomes("act-cp")) == 1
    assert control.get_action_experience("act-cp") is not None


# 28. AutonomyModule IoC Integration
def test_28_autonomy_module_ioc_integration() -> None:
    container = DependencyContainer()
    config = ConfigurationManager()
    bus = EventBus()

    module = AutonomyModule(config=config, container=container, event_bus=bus)
    module.on_initialize()

    assert container.has(RuntimeExperienceStore) is True
    assert container.has(RuntimeExperienceEngine) is True

    resolved_engine = container.resolve(RuntimeExperienceEngine)
    assert isinstance(resolved_engine, RuntimeExperienceEngine)

    snap = module.get_experience_snapshot()
    assert snap is not None
    assert snap.total_outcomes == 0


# 29. Diagnostics Snapshot Immutability
def test_29_diagnostics_snapshot_immutability() -> None:
    engine = RuntimeExperienceEngine()
    snap = engine.get_experience_snapshot()
    assert isinstance(snap, ExperienceStatusSnapshot)
    try:
        snap.total_outcomes = 100  # type: ignore[misc]
        raise AssertionError("ExperienceStatusSnapshot should be frozen")
    except AttributeError:
        pass


# 30. Configuration Disabled Behavior
def test_30_config_disabled_behavior() -> None:
    config = ConfigurationManager()
    config.set("autonomy.experience_enabled", False)
    engine = RuntimeExperienceEngine(config=config)

    rec = OutcomeRecord(
        execution_id="e-dis-1",
        action_id="act-dis",
        outcome_type=OutcomeType.SUCCESS,
        success=True,
    )
    res = engine.record_outcome(rec)
    assert res is None
    assert engine.store.count() == 0  # Not recorded when disabled!


# 31. History Limit Configuration
def test_31_history_limit_query() -> None:
    engine = RuntimeExperienceEngine()
    for i in range(15):
        rec = OutcomeRecord(
            execution_id=f"e-lim-{i}",
            action_id="act-lim",
            outcome_type=OutcomeType.SUCCESS,
            success=True,
        )
        engine.record_outcome(rec)

    outcomes = engine.get_recent_outcomes("act-lim", limit=5)
    assert len(outcomes) == 5


# 32. Stage 10 Governance Compatibility
def test_32_stage10_governance_compatibility() -> None:
    bus = EventBus()
    governance = RuntimeGovernanceEngine(event_bus=bus)
    experience = RuntimeExperienceEngine(event_bus=bus)

    governance.set_authority_scope(AutonomyScope.DISABLED)
    snap = governance.get_governance_snapshot()
    assert snap.scope == AutonomyScope.DISABLED

    # Experience recommendations do NOT alter Governance scope!
    rec = OutcomeRecord(
        execution_id="e-gov-1",
        action_id="act-gov",
        outcome_type=OutcomeType.FAILURE,
        success=False,
    )
    experience.record_outcome(rec)

    # Governance scope remains DISABLED!
    assert governance.get_governance_snapshot().scope == AutonomyScope.DISABLED


# 33. Stage 11 Policy Compatibility
def test_33_stage11_policy_compatibility() -> None:
    clock = TestClock("2026-08-19T00:00:00Z")
    policy = RuntimePolicyEngine(clock=clock)
    experience = RuntimeExperienceEngine(clock=clock)

    # Policy snapshot unaffected by experience recording
    snap = policy.get_policy_snapshot()
    assert snap is not None

    rec = OutcomeRecord(
        execution_id="e-pol-1",
        action_id="act-pol",
        outcome_type=OutcomeType.SUCCESS,
        success=True,
    )
    experience.record_outcome(rec)

    assert policy.get_policy_snapshot().total_evaluations == snap.total_evaluations


# 34. Stage 12 Execution Compatibility
def test_34_stage12_execution_compatibility() -> None:
    clock = TestClock("2026-08-19T00:00:00Z")
    execution = RuntimeExecutionEngine(clock=clock)
    experience = RuntimeExperienceEngine(clock=clock)

    action = RuntimeAction("act-st12", "Stage12Action", execute_fn=lambda ctx: "res")
    ctx = ExecutionContext("e-st12-1", "g1", "s1", "key-st12", "2026-08-19T00:00:00Z")

    res = execution.execute(action, context=ctx)
    assert res.success is True

    # Record ExecutionResult in Experience Engine
    rec = experience.record_execution_result(res, action_id=action.action_id)
    assert rec is not None
    assert experience.store.count() == 1


# 35. Full Stage 1-12 Pipeline & Experience Integration
def test_35_full_pipeline_with_experience() -> None:
    clock = TestClock("2026-08-19T00:00:00Z")
    bus = EventBus()
    memory_store = SQLiteMemoryStore(db_path=":memory:")
    store = ScheduleStore(store=memory_store)
    goals = CognitionGoalManager(store=GoalStore(store=memory_store))

    policy = RuntimePolicyEngine(clock=clock, event_bus=bus)
    governance = RuntimeGovernanceEngine(clock=clock, event_bus=bus)
    execution = RuntimeExecutionEngine(clock=clock, event_bus=bus)
    experience = RuntimeExperienceEngine(clock=clock, event_bus=bus)

    dispatcher = ScheduleDispatcher(
        schedule_store=store,
        goal_manager=goals,
        event_bus=bus,
        policy_engine=policy,
        governance_engine=governance,
        execution_engine=execution,
    )

    sched = create_test_schedule(goals, "s-full-exp")
    store.save_schedule(sched)

    # Dispatch schedule -> Policy -> Governance -> Execution -> Experience!
    res = dispatcher._dispatch_single_schedule(sched, now_iso=clock.now_iso(), execute_goals=True)
    assert res.dispatched is True

    # Stage 13 observed Stage 12 event and recorded outcome!
    assert experience.store.count() >= 1
    snap = experience.get_experience_snapshot()
    assert snap.total_outcomes >= 1
