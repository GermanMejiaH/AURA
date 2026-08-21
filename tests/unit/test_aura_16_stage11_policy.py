from __future__ import annotations

import threading
from unittest.mock import MagicMock

from aura.autonomy.module import AutonomyModule
from aura.cognition.goals import GoalManager as CognitionGoalManager
from aura.cognition.goals import GoalStore
from aura.cognition.scheduling.clock import TestClock
from aura.cognition.scheduling.control import RuntimeControlPlane
from aura.cognition.scheduling.dispatcher import ScheduleDispatcher
from aura.cognition.scheduling.governance import (
    AutonomyScope,
    RuntimeGovernanceEngine,
)
from aura.cognition.scheduling.models import ScheduleStatus, ScheduleType, TemporalSchedule
from aura.cognition.scheduling.resolution import (
    ConflictType,
    PolicyAction,
    PolicyPriority,
    PolicyStatusSnapshot,
    RuntimePolicyEngine,
)
from aura.cognition.scheduling.store import ScheduleStore
from aura.config.manager import ConfigurationManager
from aura.container import DependencyContainer
from aura.events.bus import EventBus
from aura.memory.store import SQLiteMemoryStore


def test_01_initial_policy_engine_state():
    """Test 01: Initial state of RuntimePolicyEngine and PolicyStatusSnapshot."""
    engine = RuntimePolicyEngine()
    snap = engine.get_policy_snapshot()

    assert snap.policy_enabled is True
    assert snap.total_evaluations == 0
    assert snap.allowed_count == 0
    assert snap.deferred_count == 0
    assert snap.cancelled_count == 0
    assert snap.blocked_count == 0
    assert snap.conflicts_detected_count == 0
    assert snap.deadlines_expired_count == 0
    assert snap.active_resource_locks == ()
    assert snap.waiting_tasks_count == 0


def test_02_effective_priority_calculation():
    """Test 02: Base priority calculation and mapping."""
    clock = TestClock("2026-08-18T10:00:00+00:00")
    engine = RuntimePolicyEngine(clock=clock)

    p_crit = engine.calculate_effective_priority(
        PolicyPriority.CRITICAL, "2026-08-18T10:00:00+00:00"
    )
    p_high = engine.calculate_effective_priority("HIGH", "2026-08-18T10:00:00+00:00")
    p_norm = engine.calculate_effective_priority("INVALID_PRIORITY", "2026-08-18T10:00:00+00:00")

    assert p_crit == 100.0
    assert p_high == 75.0
    assert p_norm == 50.0  # Fallback to NORMAL


def test_03_priority_aging_and_limit():
    """Test 03: Deterministic priority aging boost over time and max boost limit."""
    clock = TestClock("2026-08-18T10:00:00+00:00")
    config = ConfigurationManager()
    config.set("autonomy.priority_aging_rate_per_minute", 2.0)
    config.set("autonomy.max_aging_boost", 20.0)

    engine = RuntimePolicyEngine(clock=clock, config=config)
    created_at = "2026-08-18T10:00:00+00:00"

    # Initial: 0 minutes elapsed
    p0 = engine.calculate_effective_priority(PolicyPriority.NORMAL, created_at)
    assert p0 == 50.0

    # Advance clock by 5 minutes -> 5 * 2.0 = 10.0 boost
    clock.advance(300.0)
    p5 = engine.calculate_effective_priority(PolicyPriority.NORMAL, created_at)
    assert p5 == 60.0

    # Advance clock by 60 minutes -> boost capped at max 20.0
    clock.advance(3300.0)
    p60 = engine.calculate_effective_priority(PolicyPriority.NORMAL, created_at)
    assert p60 == 70.0


def test_04_priority_aging_disabled():
    """Test 04: Priority aging can be disabled via configuration."""
    clock = TestClock("2026-08-18T10:00:00+00:00")
    config = ConfigurationManager()
    config.set("autonomy.priority_aging_enabled", False)

    engine = RuntimePolicyEngine(clock=clock, config=config)
    clock.advance(3600.0)

    p = engine.calculate_effective_priority(PolicyPriority.LOW, "2026-08-18T10:00:00+00:00")
    assert p == 25.0  # Unchanged base LOW weight


def test_05_deadline_valid_execution():
    """Test 05: Schedule with future deadline is allowed."""
    clock = TestClock("2026-08-18T10:00:00+00:00")
    engine = RuntimePolicyEngine(clock=clock)

    sched = TemporalSchedule(
        schedule_id="sched_future_dl",
        goal_id="goal_1",
        created_at="2026-08-18T09:55:00+00:00",
        metadata={"deadline_at": "2026-08-18T10:30:00+00:00"},
    )

    dec = engine.evaluate_schedule(sched)
    assert dec.allowed is True
    assert dec.action == PolicyAction.ALLOW


def test_06_deadline_expired_cancellation():
    """Test 06: Schedule with past deadline is cancelled."""
    clock = TestClock("2026-08-18T10:00:00+00:00")
    engine = RuntimePolicyEngine(clock=clock)

    sched = TemporalSchedule(
        schedule_id="sched_past_dl",
        goal_id="goal_2",
        created_at="2026-08-18T09:00:00+00:00",
        metadata={"deadline_at": "2026-08-18T09:30:00+00:00"},
    )

    dec = engine.evaluate_schedule(sched)
    assert dec.allowed is False
    assert dec.action == PolicyAction.CANCEL
    assert dec.reason == "deadline_expired"
    assert dec.conflict is not None
    assert dec.conflict.conflict_type == ConflictType.DEADLINE_EXPIRED

    snap = engine.get_policy_snapshot()
    assert snap.cancelled_count == 1
    assert snap.deadlines_expired_count == 1


def test_07_deadline_enforcement_disabled():
    """Test 07: Expired deadline is allowed when deadline enforcement is disabled."""
    clock = TestClock("2026-08-18T10:00:00+00:00")
    config = ConfigurationManager()
    config.set("autonomy.deadline_enforcement_enabled", False)

    engine = RuntimePolicyEngine(clock=clock, config=config)
    sched = TemporalSchedule(
        schedule_id="sched_past_dl_disabled",
        goal_id="goal_3",
        created_at="2026-08-18T09:00:00+00:00",
        metadata={"deadline_at": "2026-08-18T09:30:00+00:00"},
    )

    dec = engine.evaluate_schedule(sched)
    assert dec.allowed is True


def test_08_duplicate_task_cancellation():
    """Test 08: Duplicate task execution key causes CANCEL."""
    clock = TestClock("2026-08-18T10:00:00+00:00")
    engine = RuntimePolicyEngine(clock=clock)

    sched1 = TemporalSchedule(
        schedule_id="sched_dup_1",
        goal_id="shared_goal_100",
        created_at="2026-08-18T10:00:00+00:00",
    )
    sched2 = TemporalSchedule(
        schedule_id="sched_dup_2",
        goal_id="shared_goal_100",
        created_at="2026-08-18T10:00:00+00:00",
    )

    dec1 = engine.evaluate_schedule(sched1)
    assert dec1.allowed is True

    dec2 = engine.evaluate_schedule(sched2)
    assert dec2.allowed is False
    assert dec2.action == PolicyAction.CANCEL
    assert dec2.reason == "duplicate_task_execution"
    assert dec2.conflict is not None
    assert dec2.conflict.conflict_type == ConflictType.DUPLICATE
    assert dec2.conflict.winning_task_id == "sched_dup_1"
    assert dec2.conflict.losing_task_id == "sched_dup_2"


def test_09_resource_conflict_deferral():
    """Test 09: Resource contention causes lower priority task to be DEFERRED."""
    clock = TestClock("2026-08-18T10:00:00+00:00")
    engine = RuntimePolicyEngine(clock=clock)

    sched_high = TemporalSchedule(
        schedule_id="sched_res_high",
        goal_id="goal_h",
        created_at="2026-08-18T10:00:00+00:00",
        metadata={"priority": "HIGH", "required_resources": ["camera_1"]},
    )
    sched_low = TemporalSchedule(
        schedule_id="sched_res_low",
        goal_id="goal_l",
        created_at="2026-08-18T10:00:00+00:00",
        metadata={"priority": "LOW", "required_resources": ["camera_1"]},
    )

    dec_h = engine.evaluate_schedule(sched_high)
    assert dec_h.allowed is True

    dec_l = engine.evaluate_schedule(sched_low)
    assert dec_l.allowed is False
    assert dec_l.action == PolicyAction.DEFER
    assert "resource_conflict" in dec_l.reason
    assert dec_l.conflict is not None
    assert dec_l.conflict.conflict_type == ConflictType.RESOURCE_CONFLICT
    assert dec_l.conflict.winning_task_id == "sched_res_high"
    assert dec_l.conflict.losing_task_id == "sched_res_low"


def test_10_higher_priority_resource_preemption():
    """Test 10: Higher priority task pre-empts resource lock held by lower priority task."""
    clock = TestClock("2026-08-18T10:00:00+00:00")
    engine = RuntimePolicyEngine(clock=clock)

    sched_low = TemporalSchedule(
        schedule_id="sched_pre_low",
        goal_id="goal_low",
        created_at="2026-08-18T10:00:00+00:00",
        metadata={"priority": "LOW", "required_resources": ["motor_1"]},
    )
    sched_crit = TemporalSchedule(
        schedule_id="sched_pre_crit",
        goal_id="goal_crit",
        created_at="2026-08-18T10:00:00+00:00",
        metadata={"priority": "CRITICAL", "required_resources": ["motor_1"]},
    )

    dec_l = engine.evaluate_schedule(sched_low)
    assert dec_l.allowed is True

    dec_c = engine.evaluate_schedule(sched_crit)
    assert dec_c.allowed is True  # Pre-empts motor_1 lock


def test_11_task_completion_releases_resources():
    """Test 11: Task completion releases resource locks and active deduplication keys."""
    clock = TestClock("2026-08-18T10:00:00+00:00")
    engine = RuntimePolicyEngine(clock=clock)

    sched1 = TemporalSchedule(
        schedule_id="sched_rel_1",
        goal_id="goal_rel",
        created_at="2026-08-18T10:00:00+00:00",
        metadata={"required_resources": ["sensor_a"]},
    )

    dec1 = engine.evaluate_schedule(sched1)
    assert dec1.allowed is True
    assert "sensor_a" in engine.get_policy_snapshot().active_resource_locks

    # Task completes
    engine.record_task_completion("sched_rel_1", success=True)
    assert "sensor_a" not in engine.get_policy_snapshot().active_resource_locks

    # Re-evaluating another schedule with same goal or resource is now allowed
    sched2 = TemporalSchedule(
        schedule_id="sched_rel_2",
        goal_id="goal_rel",
        created_at="2026-08-18T10:01:00+00:00",
        metadata={"required_resources": ["sensor_a"]},
    )
    dec2 = engine.evaluate_schedule(sched2)
    assert dec2.allowed is True


def test_12_event_bus_publishing():
    """Test 12: Stage 11 policy events published cleanly to EventBus."""
    event_bus = EventBus()
    published_events: list[str] = []

    event_bus.subscribe(
        "RuntimePolicyDecisionMade", lambda e: published_events.append("DecisionMade")
    )
    event_bus.subscribe(
        "RuntimePolicyConflictDetected", lambda e: published_events.append("ConflictDetected")
    )
    event_bus.subscribe("RuntimeTaskCancelled", lambda e: published_events.append("TaskCancelled"))

    clock = TestClock("2026-08-18T10:00:00+00:00")
    engine = RuntimePolicyEngine(clock=clock, event_bus=event_bus)

    sched_expired = TemporalSchedule(
        schedule_id="sched_exp_evt",
        goal_id="goal_evt",
        created_at="2026-08-18T08:00:00+00:00",
        metadata={"deadline_at": "2026-08-18T09:00:00+00:00"},
    )

    engine.evaluate_schedule(sched_expired)
    assert "DecisionMade" in published_events
    assert "ConflictDetected" in published_events
    assert "TaskCancelled" in published_events


def test_13_dispatcher_policy_integration():
    """Test 13: ScheduleDispatcher respects RuntimePolicyEngine decisions."""
    memory_store = SQLiteMemoryStore(db_path=":memory:")
    schedule_store = ScheduleStore(store=memory_store)
    goal_mgr = CognitionGoalManager(store=GoalStore(store=memory_store))
    goal = goal_mgr.create_goal("Test policy goal")

    clock = TestClock("2026-08-18T10:00:00+00:00")
    policy_engine = RuntimePolicyEngine(clock=clock)

    dispatcher = ScheduleDispatcher(
        schedule_store=schedule_store,
        goal_manager=goal_mgr,
        policy_engine=policy_engine,
    )

    sched = TemporalSchedule(
        schedule_id="sched_pol_disp",
        goal_id=goal.goal_id,
        schedule_type=ScheduleType.INTERVAL,
        expression="30s",
        status=ScheduleStatus.ACTIVE,
        created_at="2026-08-18T08:00:00+00:00",
        metadata={"deadline_at": "2026-08-18T09:00:00+00:00"},
    )
    schedule_store.save_schedule(sched)

    results = dispatcher.process_due_schedules(at_timestamp="2026-08-18T10:00:00+00:00")
    assert len(results) == 1
    assert not results[0].dispatched
    assert "Policy blocked/deferred execution" in results[0].reason


def test_14_policy_precedes_governance_barrier():
    """Test 14: Policy evaluation runs BEFORE Governance evaluation (Policy -> Governance)."""
    memory_store = SQLiteMemoryStore(db_path=":memory:")
    schedule_store = ScheduleStore(store=memory_store)
    goal_mgr = CognitionGoalManager(store=GoalStore(store=memory_store))
    goal = goal_mgr.create_goal("Order test goal")

    clock = TestClock("2026-08-18T10:00:00+00:00")
    policy_engine = RuntimePolicyEngine(clock=clock)
    governance_engine = MagicMock(spec=RuntimeGovernanceEngine)

    dispatcher = ScheduleDispatcher(
        schedule_store=schedule_store,
        goal_manager=goal_mgr,
        governance_engine=governance_engine,
        policy_engine=policy_engine,
    )

    # Schedule is expired by Policy
    sched = TemporalSchedule(
        schedule_id="sched_order_test",
        goal_id=goal.goal_id,
        schedule_type=ScheduleType.INTERVAL,
        expression="30s",
        status=ScheduleStatus.ACTIVE,
        created_at="2026-08-18T08:00:00+00:00",
        metadata={"deadline_at": "2026-08-18T09:00:00+00:00"},
    )
    schedule_store.save_schedule(sched)

    results = dispatcher.process_due_schedules(at_timestamp="2026-08-18T10:00:00+00:00")
    assert len(results) == 1
    assert not results[0].dispatched
    assert "Policy blocked/deferred execution" in results[0].reason
    # Governance was NOT invoked because Policy blocked first!
    governance_engine.evaluate_action.assert_not_called()


def test_15_governance_blocks_allowed_policy():
    """Test 15: Policy ALLOW decision CANNOT bypass Stage 10 Governance block."""
    memory_store = SQLiteMemoryStore(db_path=":memory:")
    schedule_store = ScheduleStore(store=memory_store)
    goal_mgr = CognitionGoalManager(store=GoalStore(store=memory_store))
    goal = goal_mgr.create_goal("Governance barrier goal")

    clock = TestClock("2026-08-18T10:00:00+00:00")
    policy_engine = RuntimePolicyEngine(clock=clock)
    governance_engine = RuntimeGovernanceEngine(clock=clock)
    governance_engine.set_authority_scope(AutonomyScope.DISABLED)

    dispatcher = ScheduleDispatcher(
        schedule_store=schedule_store,
        goal_manager=goal_mgr,
        governance_engine=governance_engine,
        policy_engine=policy_engine,
    )

    sched = TemporalSchedule(
        schedule_id="sched_gov_block_test",
        goal_id=goal.goal_id,
        schedule_type=ScheduleType.INTERVAL,
        expression="30s",
        status=ScheduleStatus.ACTIVE,
        created_at="2026-08-18T10:00:00+00:00",
    )
    schedule_store.save_schedule(sched)

    results = dispatcher.process_due_schedules(at_timestamp="2026-08-18T10:00:00+00:00")
    assert len(results) == 1
    assert not results[0].dispatched
    assert "Governance blocked execution" in results[0].reason


def test_16_control_plane_policy_integration():
    """Test 16: RuntimeControlPlane.get_policy_snapshot() returns policy snapshot."""
    runtime = MagicMock()
    policy_engine = RuntimePolicyEngine()

    cp = RuntimeControlPlane(runtime=runtime, policy_engine=policy_engine)
    snap = cp.get_policy_snapshot()
    assert snap is not None
    assert isinstance(snap, PolicyStatusSnapshot)
    assert snap.policy_enabled is True


def test_17_autonomy_module_ioc_integration():
    """Test 17: AutonomyModule.on_initialize() resolves and registers RuntimePolicyEngine in IoC."""
    container = DependencyContainer()
    config = ConfigurationManager()

    module = AutonomyModule(config=config, container=container)
    module.on_initialize()

    assert module.runtime_policy_engine is not None
    assert container.has(RuntimePolicyEngine)
    resolved = container.resolve(RuntimePolicyEngine)
    assert resolved is module.runtime_policy_engine
    assert module.get_policy_snapshot() is not None


def test_18_multithreaded_concurrent_policy_evaluations():
    """Test 18: Multithreaded concurrent evaluations operate cleanly and thread-safe."""
    engine = RuntimePolicyEngine()
    exceptions: list[Exception] = []

    def _worker(worker_id: int):
        try:
            for i in range(10):
                sched = TemporalSchedule(
                    schedule_id=f"sched_thread_{worker_id}_{i}",
                    goal_id=f"goal_thread_{worker_id}",
                    metadata={"priority": "NORMAL"},
                )
                engine.evaluate_schedule(sched)
        except Exception as exc:
            exceptions.append(exc)

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(exceptions) == 0
    snap = engine.get_policy_snapshot()
    assert snap.total_evaluations == 50


def test_19_policy_resolution_disabled_bypass():
    """Test 19: Disabling policy_resolution_enabled allows schedules through."""
    config = ConfigurationManager()
    config.set("autonomy.policy_resolution_enabled", False)

    engine = RuntimePolicyEngine(config=config)
    sched_expired = TemporalSchedule(
        schedule_id="sched_bypass_exp",
        goal_id="goal_bypass",
        created_at="2026-08-18T08:00:00+00:00",
        metadata={"deadline_at": "2026-08-18T09:00:00+00:00"},
    )

    dec = engine.evaluate_schedule(sched_expired)
    assert dec.allowed is True
    assert dec.reason == "policy_resolution_disabled"


def test_20_stage1_to_stage10_compatibility():
    """Test 20: Full backward compatibility with Stages 1-10 components."""
    memory_store = SQLiteMemoryStore(db_path=":memory:")
    schedule_store = ScheduleStore(store=memory_store)
    goal_mgr = CognitionGoalManager(store=GoalStore(store=memory_store))
    goal = goal_mgr.create_goal("Compatibility goal")

    clock = TestClock("2026-08-18T10:00:00+00:00")
    governance_engine = RuntimeGovernanceEngine(clock=clock)
    policy_engine = RuntimePolicyEngine(clock=clock)

    dispatcher = ScheduleDispatcher(
        schedule_store=schedule_store,
        goal_manager=goal_mgr,
        governance_engine=governance_engine,
        policy_engine=policy_engine,
    )

    sched = TemporalSchedule(
        schedule_id="sched_compat_10",
        goal_id=goal.goal_id,
        schedule_type=ScheduleType.ONE_SHOT,
        next_run_at="2026-08-18T09:50:00+00:00",
        status=ScheduleStatus.ACTIVE,
    )
    schedule_store.save_schedule(sched)

    results = dispatcher.process_due_schedules(at_timestamp="2026-08-18T10:00:00+00:00")
    assert len(results) == 1
    assert results[0].dispatched is True
