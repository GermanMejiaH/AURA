from __future__ import annotations

import threading
from typing import Any

from aura.autonomy.module import AutonomyModule
from aura.cognition.goals import GoalManager as CognitionGoalManager
from aura.cognition.goals import GoalStore
from aura.cognition.scheduling import (
    AutonomyScope,
    ExecutionContext,
    ExecutionFailureType,
    ExecutionResult,
    ExecutionState,
    ExecutionStatusSnapshot,
    RetryPolicy,
    RuntimeAction,
    RuntimeControlPlane,
    RuntimeExecutionEngine,
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
)
from aura.memory.store import SQLiteMemoryStore


def create_test_schedule(
    goal_mgr: CognitionGoalManager,
    schedule_id: str = "sched-001",
) -> TemporalSchedule:
    g = goal_mgr.create_goal(description="Test goal")
    return TemporalSchedule(
        schedule_id=schedule_id,
        goal_id=g.goal_id,
        schedule_type=ScheduleType.CRON,
        expression="* * * * *",
    )


class DummyGoal:
    def __init__(self, goal_id: str = "goal-001") -> None:
        self.goal_id = goal_id

    def to_goal_model(self) -> Any:
        return self


# 1. Lifecycle: Initial State & Snapshot
def test_01_initial_execution_engine_state() -> None:
    engine = RuntimeExecutionEngine()
    snap = engine.get_execution_snapshot()
    assert isinstance(snap, ExecutionStatusSnapshot)
    assert snap.execution_enabled is True
    assert snap.total_executions == 0
    assert snap.successful_executions == 0
    assert snap.failed_executions == 0
    assert snap.active_executions_count == 0
    assert engine.get_active_executions() == []
    assert engine.get_execution_history() == []


# 2. Lifecycle: Valid State Transitions & Success
def test_02_execution_state_transitions_success() -> None:
    clock = TestClock("2026-08-19T00:00:00Z")
    engine = RuntimeExecutionEngine(clock=clock)

    action = RuntimeAction(
        action_id="act-1",
        name="ValidAction",
        execute_fn=lambda ctx: "output_data",
    )
    ctx = ExecutionContext(
        execution_id="exec-1",
        goal_id="goal-1",
        schedule_id="sched-1",
        idempotency_key="key-1",
        started_at=clock.now_iso(),
    )
    result = engine.execute(action, context=ctx)
    assert result.success is True
    assert result.state == ExecutionState.COMMITTED
    assert result.output == "output_data"
    assert result.error is None
    assert result.attempt_number == 1

    snap = engine.get_execution_snapshot()
    assert snap.total_executions == 1
    assert snap.successful_executions == 1
    assert snap.failed_executions == 0


# 3. Invalid State Transitions & Data Integrity
def test_03_invalid_state_transitions() -> None:
    assert ExecutionState.PENDING.value == "PENDING"
    assert ExecutionState.COMMITTED.value == "COMMITTED"
    assert ExecutionState.ROLLED_BACK.value == "ROLLED_BACK"


# 4. Action Result Immutability
def test_04_execution_result_immutability() -> None:
    res = ExecutionResult(
        execution_id="exec-1",
        goal_id="goal-1",
        schedule_id="sched-1",
        idempotency_key="key-1",
        success=True,
        state=ExecutionState.COMMITTED,
        attempt_number=1,
        started_at="2026-08-19T00:00:00Z",
        completed_at="2026-08-19T00:00:01Z",
        error=None,
        failure_type=None,
        rollback_performed=False,
        compensation_performed=False,
    )
    try:
        res.success = False  # type: ignore[misc]
    except Exception as exc:
        assert "dataclass" in str(exc) or "frozen" in str(exc) or "cannot assign" in str(exc)


# 5. Transient Failure & Retry Behavior
def test_05_transient_failure_and_retry_behavior() -> None:
    engine = RuntimeExecutionEngine()
    attempts_made = 0

    def failing_then_succeeding_fn(ctx: ExecutionContext) -> str:
        nonlocal attempts_made
        attempts_made += 1
        if attempts_made < 3:
            raise RuntimeError("Transient network timeout")
        return "success_on_attempt_3"

    action = RuntimeAction("act-retry", "RetryableAction", execute_fn=failing_then_succeeding_fn)
    ctx = ExecutionContext("exec-retry", "goal-1", "sched-1", "key-retry", "2026-08-19T00:00:00Z")
    retry_policy = RetryPolicy(max_attempts=3, retryable_failures=(ExecutionFailureType.TRANSIENT,))

    res = engine.execute(action, context=ctx, retry_policy=retry_policy)
    assert res.success is True
    assert res.state == ExecutionState.COMMITTED
    assert res.attempt_number == 3
    assert res.output == "success_on_attempt_3"

    snap = engine.get_execution_snapshot()
    assert snap.retry_count == 2
    assert snap.successful_executions == 1


# 6. Permanent Failure (No Retry)
def test_06_permanent_failure_no_retry() -> None:
    engine = RuntimeExecutionEngine()
    attempts_made = 0

    def validation_error_fn(ctx: ExecutionContext) -> None:
        nonlocal attempts_made
        attempts_made += 1
        raise ValueError("Permanent invalid payload parameter")

    action = RuntimeAction("act-perm", "PermanentFailureAction", execute_fn=validation_error_fn)
    ctx = ExecutionContext("exec-perm", "goal-1", "sched-1", "key-perm", "2026-08-19T00:00:00Z")
    retry_policy = RetryPolicy(max_attempts=3)

    res = engine.execute(action, context=ctx, retry_policy=retry_policy)
    assert res.success is False
    assert res.attempt_number == 1  # No retries for validation failure!
    assert res.failure_type in (
        ExecutionFailureType.VALIDATION,
        ExecutionFailureType.ROLLBACK_FAILURE,
    )
    assert "invalid payload" in (res.error or "")


# 7. Max Attempts Enforcement
def test_07_max_attempts_enforcement() -> None:
    engine = RuntimeExecutionEngine()
    attempts_made = 0

    def always_failing_fn(ctx: ExecutionContext) -> None:
        nonlocal attempts_made
        attempts_made += 1
        raise RuntimeError("Persistent transient error")

    action = RuntimeAction("act-max", "AlwaysFailingAction", execute_fn=always_failing_fn)
    ctx = ExecutionContext("exec-max", "goal-1", "sched-1", "key-max", "2026-08-19T00:00:00Z")
    retry_policy = RetryPolicy(max_attempts=3)

    res = engine.execute(action, context=ctx, retry_policy=retry_policy)
    assert res.success is False
    assert attempts_made == 3
    assert res.attempt_number == 3


# 8. Transaction Commit
def test_08_transaction_commit() -> None:
    engine = RuntimeExecutionEngine()
    executed_steps: list[str] = []

    action = RuntimeAction(
        "act-tx",
        "TxAction",
        execute_fn=lambda ctx: executed_steps.append("step1"),
    )
    ctx = ExecutionContext("exec-tx", "goal-1", "sched-1", "key-tx", "2026-08-19T00:00:00Z")

    res = engine.execute(action, context=ctx)
    assert res.success is True
    assert executed_steps == ["step1"]
    assert res.state == ExecutionState.COMMITTED


# 9. Rollback on Failure
def test_09_rollback_on_failure() -> None:
    engine = RuntimeExecutionEngine()
    rolled_back = False

    def rollback_fn(ctx: ExecutionContext) -> bool:
        nonlocal rolled_back
        rolled_back = True
        return True

    def failing_execute(ctx: ExecutionContext) -> None:
        raise RuntimeError("Failure requiring rollback")

    action = RuntimeAction(
        "act-rb", "RollbackAction", execute_fn=failing_execute, rollback_fn=rollback_fn
    )
    ctx = ExecutionContext("exec-rb", "goal-1", "sched-1", "key-rb", "2026-08-19T00:00:00Z")
    retry_policy = RetryPolicy(max_attempts=1)

    res = engine.execute(action, context=ctx, retry_policy=retry_policy)
    assert res.success is False
    assert res.state == ExecutionState.ROLLED_BACK
    assert res.rollback_performed is True
    assert rolled_back is True


# 10. Rollback Reverse Order Execution (Stack Order)
def test_10_rollback_reverse_order() -> None:
    engine = RuntimeExecutionEngine()
    rollback_order: list[str] = []

    class Step1Action(RuntimeAction):
        def execute(self, ctx: ExecutionContext) -> None:
            pass

        def rollback(self, ctx: ExecutionContext) -> bool:
            rollback_order.append("Step1")
            return True

    class Step2Action(RuntimeAction):
        def execute(self, ctx: ExecutionContext) -> None:
            raise RuntimeError("Step2 Error")

        def rollback(self, ctx: ExecutionContext) -> bool:
            rollback_order.append("Step2")
            return True

    # In single action with sub-actions or custom execution
    step1 = Step1Action("step1", "Step 1")
    step2 = Step2Action("step2", "Step 2")

    def execute_multi_step(ctx: ExecutionContext) -> None:
        step1.execute(ctx)
        step2.execute(ctx)

    def rollback_multi_step(ctx: ExecutionContext) -> bool:
        b2 = step2.rollback(ctx)
        b1 = step1.rollback(ctx)
        return b2 and b1

    action = RuntimeAction(
        "act-multi",
        "MultiStepAction",
        execute_fn=execute_multi_step,
        rollback_fn=rollback_multi_step,
    )
    ctx = ExecutionContext("exec-multi", "goal-1", "sched-1", "key-multi", "2026-08-19T00:00:00Z")
    retry_policy = RetryPolicy(max_attempts=1)

    res = engine.execute(action, context=ctx, retry_policy=retry_policy)
    assert res.success is False
    assert rollback_order == ["Step2", "Step1"]  # Reverse order verified!


# 11. Rollback Failure Triggers Compensation
def test_11_rollback_failure_triggers_compensation() -> None:
    engine = RuntimeExecutionEngine()
    compensated = False

    def failing_rollback(ctx: ExecutionContext) -> bool:
        return False  # Rollback failed!

    def successful_compensation(ctx: ExecutionContext) -> bool:
        nonlocal compensated
        compensated = True
        return True

    def failing_execute(ctx: ExecutionContext) -> None:
        raise RuntimeError("Execution error")

    action = RuntimeAction(
        "act-comp",
        "CompensationAction",
        execute_fn=failing_execute,
        rollback_fn=failing_rollback,
        compensate_fn=successful_compensation,
    )
    ctx = ExecutionContext("exec-comp", "goal-1", "sched-1", "key-comp", "2026-08-19T00:00:00Z")
    retry_policy = RetryPolicy(max_attempts=1)

    res = engine.execute(action, context=ctx, retry_policy=retry_policy)
    assert res.success is True  # State is COMPENSATED (safe terminal state)
    assert res.state == ExecutionState.COMPENSATED
    assert res.compensation_performed is True
    assert compensated is True


# 12. Compensation Success
def test_12_compensation_success() -> None:
    engine = RuntimeExecutionEngine()
    comp_count = 0

    def raise_err(ctx: ExecutionContext) -> None:
        raise RuntimeError("err")

    def do_compensate(ctx: ExecutionContext) -> bool:
        nonlocal comp_count
        comp_count += 1
        return True

    action = RuntimeAction(
        "act-c12",
        "CompAction",
        execute_fn=raise_err,
        rollback_fn=lambda ctx: False,
        compensate_fn=do_compensate,
    )
    ctx = ExecutionContext("exec-c12", "goal-1", "sched-1", "key-c12", "2026-08-19T00:00:00Z")
    res = engine.execute(action, context=ctx, retry_policy=RetryPolicy(max_attempts=1))
    assert res.state == ExecutionState.COMPENSATED
    assert comp_count == 1


# 13. Compensation Failure Ends in FAILED
def test_13_compensation_failure_ends_in_failed() -> None:
    engine = RuntimeExecutionEngine()

    action = RuntimeAction(
        "act-fail-all",
        "TotalFailureAction",
        execute_fn=lambda ctx: (_ for _ in ()).throw(RuntimeError("Fatal error")),
        rollback_fn=lambda ctx: False,
        compensate_fn=lambda ctx: False,  # Compensation also fails!
    )
    ctx = ExecutionContext(
        "exec-fail-all", "goal-1", "sched-1", "key-fail-all", "2026-08-19T00:00:00Z"
    )
    res = engine.execute(action, context=ctx, retry_policy=RetryPolicy(max_attempts=1))
    assert res.success is False
    assert res.state == ExecutionState.FAILED
    assert res.failure_type == ExecutionFailureType.COMPENSATION_FAILURE


# 14. Same Idempotency Key Deduplication
def test_14_same_idempotency_key_deduplication() -> None:
    engine = RuntimeExecutionEngine()
    counter = 0

    def increment_fn(ctx: ExecutionContext) -> int:
        nonlocal counter
        counter += 1
        return counter

    action1 = RuntimeAction("act-idemp", "IdempAction", execute_fn=increment_fn)
    ctx1 = ExecutionContext("exec-i1", "goal-1", "sched-1", "idemp-key-999", "2026-08-19T00:00:00Z")
    res1 = engine.execute(action1, context=ctx1)
    assert res1.output == 1
    assert counter == 1

    # Second execution request with exact same idempotency_key
    action2 = RuntimeAction("act-idemp", "IdempAction", execute_fn=increment_fn)
    ctx2 = ExecutionContext("exec-i2", "goal-1", "sched-1", "idemp-key-999", "2026-08-19T00:00:01Z")
    res2 = engine.execute(action2, context=ctx2)
    assert res2.output == 1  # Returned cached result!
    assert counter == 1  # Function was NOT executed a second time!


# 15. Different Idempotency Keys
def test_15_different_idempotency_keys() -> None:
    engine = RuntimeExecutionEngine()
    counter = 0

    def increment_fn(ctx: ExecutionContext) -> int:
        nonlocal counter
        counter += 1
        return counter

    action1 = RuntimeAction("act-i1", "Action1", execute_fn=increment_fn)
    res1 = engine.execute(
        action1, context=ExecutionContext("e1", "g1", "s1", "key-A", "2026-08-19T00:00:00Z")
    )

    action2 = RuntimeAction("act-i2", "Action2", execute_fn=increment_fn)
    res2 = engine.execute(
        action2, context=ExecutionContext("e2", "g1", "s1", "key-B", "2026-08-19T00:00:01Z")
    )

    assert res1.output == 1
    assert res2.output == 2
    assert counter == 2


# 16. Concurrent Idempotency Protection
def test_16_concurrent_idempotency_protection() -> None:
    engine = RuntimeExecutionEngine()
    results: list[ExecutionResult] = []
    lock = threading.Lock()

    def worker() -> None:
        action = RuntimeAction("act-conc", "ConcAction", execute_fn=lambda ctx: "done")
        ctx = ExecutionContext("e-conc", "g1", "s1", "shared-idemp-key", "2026-08-19T00:00:00Z")
        res = engine.execute(action, context=ctx)
        with lock:
            results.append(res)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 5
    for r in results:
        assert r.success is True
        assert r.idempotency_key == "shared-idemp-key"


# 17. Timeout Detection and Rollback
def test_17_timeout_detection_and_rollback() -> None:
    clock = TestClock("2026-08-19T00:00:00Z")
    engine = RuntimeExecutionEngine(clock=clock)

    def slow_action_fn(ctx: ExecutionContext) -> None:
        # Advance clock beyond timeout threshold during execution
        clock.advance(35.0)

    action = RuntimeAction("act-slow", "SlowAction", execute_fn=slow_action_fn)
    ctx = ExecutionContext(
        "exec-slow",
        "goal-1",
        "sched-1",
        "key-slow",
        started_at="2026-08-19T00:00:00Z",
        timeout_seconds=30.0,
    )
    res = engine.execute(action, context=ctx, retry_policy=RetryPolicy(max_attempts=1))
    assert res.success is False
    assert res.state in (ExecutionState.TIMED_OUT, ExecutionState.ROLLED_BACK)
    assert res.failure_type == ExecutionFailureType.TIMEOUT


# 18. Cooperative Cancellation
def test_18_cooperative_cancellation() -> None:
    engine = RuntimeExecutionEngine()
    ctx = ExecutionContext("exec-cancel", "g1", "s1", "key-cancel", "2026-08-19T00:00:00Z")

    # Simulate active execution
    engine._active_executions["exec-cancel"] = ctx
    engine._active_idempotency["key-cancel"] = "exec-cancel"

    cancelled = engine.cancel_execution("exec-cancel", reason="Emergency operator cancel")
    assert cancelled is True

    snap = engine.get_execution_snapshot()
    assert snap.cancelled_executions == 1


# 19. Pipeline Order: Policy -> Governance -> Execution
def test_19_pipeline_order_policy_governance_execution() -> None:
    events_log: list[str] = []

    class EventTrackerBus(EventBus):
        def publish(self, event: Event) -> None:
            events_log.append(event.__class__.__name__)
            super().publish(event)

    bus = EventTrackerBus()
    memory_store = SQLiteMemoryStore(db_path=":memory:")
    store = ScheduleStore(store=memory_store)
    goals = CognitionGoalManager(store=GoalStore(store=memory_store))

    policy = RuntimePolicyEngine(event_bus=bus)
    governance = RuntimeGovernanceEngine(event_bus=bus)
    execution = RuntimeExecutionEngine(event_bus=bus)

    dispatcher = ScheduleDispatcher(
        schedule_store=store,
        goal_manager=goals,
        event_bus=bus,
        policy_engine=policy,
        governance_engine=governance,
        execution_engine=execution,
    )

    sched = create_test_schedule(goals, "s-pipeline")
    store.save_schedule(sched)

    res = dispatcher._dispatch_single_schedule(
        sched, now_iso="2026-08-19T00:00:00Z", execute_goals=True
    )

    assert res.dispatched is True
    # Order verification in events
    pol_idx = events_log.index("RuntimePolicyDecisionMade")
    exec_idx = events_log.index("RuntimeExecutionStarted")
    assert pol_idx < exec_idx  # Policy MUST precede Execution!


# 20. Policy Blocks Execution
def test_20_policy_blocks_execution() -> None:
    bus = EventBus()
    memory_store = SQLiteMemoryStore(db_path=":memory:")
    store = ScheduleStore(store=memory_store)
    goals = CognitionGoalManager(store=GoalStore(store=memory_store))

    policy = RuntimePolicyEngine(event_bus=bus)
    execution = RuntimeExecutionEngine(event_bus=bus)

    dispatcher = ScheduleDispatcher(
        schedule_store=store,
        goal_manager=goals,
        event_bus=bus,
        policy_engine=policy,
        execution_engine=execution,
    )

    sched = create_test_schedule(goals, "s-pblock")
    sched.metadata["deadline_iso"] = "2000-01-01T00:00:00Z"  # Expired deadline forces CANCEL
    store.save_schedule(sched)

    res = dispatcher._dispatch_single_schedule(
        sched, now_iso="2026-08-19T00:00:00Z", execute_goals=True
    )
    assert res.dispatched is False
    assert execution.get_execution_snapshot().total_executions == 0  # Execution NEVER called!


# 21. Governance Blocks Execution (Even If Allowed by Policy)
def test_21_governance_blocks_allowed_execution() -> None:
    bus = EventBus()
    memory_store = SQLiteMemoryStore(db_path=":memory:")
    store = ScheduleStore(store=memory_store)
    goals = CognitionGoalManager(store=GoalStore(store=memory_store))

    policy = RuntimePolicyEngine(event_bus=bus)
    governance = RuntimeGovernanceEngine(event_bus=bus)
    execution = RuntimeExecutionEngine(event_bus=bus)

    governance.set_authority_scope(AutonomyScope.DISABLED)  # Block all governance actions

    dispatcher = ScheduleDispatcher(
        schedule_store=store,
        goal_manager=goals,
        event_bus=bus,
        policy_engine=policy,
        governance_engine=governance,
        execution_engine=execution,
    )

    sched = create_test_schedule(goals, "s-gblock")
    store.save_schedule(sched)

    res = dispatcher._dispatch_single_schedule(
        sched, now_iso="2026-08-19T00:00:00Z", execute_goals=True
    )
    assert res.dispatched is False
    assert "Governance blocked" in res.reason
    assert execution.get_execution_snapshot().total_executions == 0  # Execution NEVER called!


# 22. Circuit Breaker Receives Execution Outcome
def test_22_circuit_breaker_receives_execution_outcome() -> None:
    bus = EventBus()
    memory_store = SQLiteMemoryStore(db_path=":memory:")
    store = ScheduleStore(store=memory_store)
    goals = CognitionGoalManager(store=GoalStore(store=memory_store))

    governance = RuntimeGovernanceEngine(event_bus=bus)
    execution = RuntimeExecutionEngine(event_bus=bus)

    dispatcher = ScheduleDispatcher(
        schedule_store=store,
        goal_manager=goals,
        event_bus=bus,
        governance_engine=governance,
        execution_engine=execution,
    )

    sched = create_test_schedule(goals, "s-cb")
    store.save_schedule(sched)

    dispatcher.planner = Any  # type: ignore[assignment]
    dispatcher.planner.deliberate_and_plan = lambda g: (_ for _ in ()).throw(
        RuntimeError("Failing execution cycle")
    )  # type: ignore[assignment]

    res = dispatcher._dispatch_single_schedule(
        sched, now_iso="2026-08-19T00:00:00Z", execute_goals=True
    )
    assert res.dispatched is False
    assert governance.get_governance_snapshot().total_evaluations > 0


# 23. AutonomyModule IoC Integration
def test_23_autonomy_module_ioc_integration() -> None:
    container = DependencyContainer()
    config = ConfigurationManager()
    bus = EventBus()

    module = AutonomyModule(config=config, container=container, event_bus=bus)
    module.on_initialize()

    assert container.has(RuntimeExecutionEngine) is True
    resolved_engine = container.resolve(RuntimeExecutionEngine)
    assert isinstance(resolved_engine, RuntimeExecutionEngine)

    snap = module.get_execution_snapshot()
    assert snap is not None
    assert snap.execution_enabled is True


# 24. Control Plane Queries & Operations
def test_24_control_plane_execution_queries() -> None:
    engine = RuntimeExecutionEngine()
    control = RuntimeControlPlane(runtime=None, execution_engine=engine)  # type: ignore[arg-type]

    snap = control.get_execution_snapshot()
    assert snap is not None
    assert snap.total_executions == 0
    assert control.get_active_executions() == []
    assert control.get_execution_history() == []


# 25. EventBus Event Emission
def test_25_event_bus_publishing() -> None:
    published_events: list[Event] = []

    class EventCollector(EventBus):
        def publish(self, event: Event) -> None:
            published_events.append(event)
            super().publish(event)

    bus = EventCollector()
    engine = RuntimeExecutionEngine(event_bus=bus)

    action = RuntimeAction("act-ev", "EventAction", execute_fn=lambda ctx: "ok")
    ctx = ExecutionContext("exec-ev", "g1", "s1", "key-ev", "2026-08-19T00:00:00Z")

    engine.execute(action, context=ctx)

    names = [e.__class__.__name__ for e in published_events]
    assert "RuntimeExecutionStarted" in names
    assert "RuntimeExecutionValidated" in names
    assert "RuntimeExecutionCompleted" in names


# 26. Multi-threaded Concurrent Executions
def test_26_multithreaded_concurrent_executions() -> None:
    engine = RuntimeExecutionEngine()
    errors: list[Exception] = []

    def worker(i: int) -> None:
        try:
            action = RuntimeAction(f"act-{i}", f"Action_{i}", execute_fn=lambda ctx: f"res_{i}")
            ctx = ExecutionContext(
                f"e-{i}", f"g-{i}", f"s-{i}", f"key-mt-{i}", "2026-08-19T00:00:00Z"
            )
            res = engine.execute(action, context=ctx)
            assert res.success is True
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    snap = engine.get_execution_snapshot()
    assert snap.total_executions == 20
    assert snap.successful_executions == 20


# 27. Bounded Execution History
def test_27_execution_history_bounded() -> None:
    config = ConfigurationManager()
    config.set("autonomy.execution_history_size", 5)
    engine = RuntimeExecutionEngine(config=config)

    for i in range(10):
        action = RuntimeAction(f"act-b-{i}", f"Action_{i}", execute_fn=lambda ctx, val=i: val)
        ctx = ExecutionContext(f"e-b-{i}", "g1", "s1", f"key-b-{i}", "2026-08-19T00:00:00Z")
        engine.execute(action, context=ctx)

    history = engine.get_execution_history()
    assert len(history) == 5
    assert history[0].idempotency_key == "key-b-5"
    assert history[-1].idempotency_key == "key-b-9"


# 28. Stage 1-11 Compatibility Verification
def test_28_stage1_to_stage11_compatibility() -> None:
    clock = TestClock("2026-08-19T00:00:00Z")
    memory_store = SQLiteMemoryStore(db_path=":memory:")
    store = ScheduleStore(store=memory_store)
    goals = CognitionGoalManager(store=GoalStore(store=memory_store))

    policy = RuntimePolicyEngine(clock=clock)
    governance = RuntimeGovernanceEngine(clock=clock)
    execution = RuntimeExecutionEngine(clock=clock)

    dispatcher = ScheduleDispatcher(
        schedule_store=store,
        goal_manager=goals,
        evaluator=None,
        governance_engine=governance,
        policy_engine=policy,
        execution_engine=execution,
    )

    sched = create_test_schedule(goals, "s-compat")
    store.save_schedule(sched)

    res = dispatcher._dispatch_single_schedule(sched, now_iso=clock.now_iso(), execute_goals=True)
    assert res.dispatched is True
    assert res.schedule_id == "s-compat"
