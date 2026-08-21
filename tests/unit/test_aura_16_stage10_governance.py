from __future__ import annotations

import threading
from unittest.mock import MagicMock

from aura.autonomy.module import AutonomyModule
from aura.cognition.goals import GoalManager, GoalStore
from aura.cognition.scheduling.clock import TestClock
from aura.cognition.scheduling.control import RuntimeControlPlane
from aura.cognition.scheduling.dispatcher import ScheduleDispatcher
from aura.cognition.scheduling.governance import (
    AutonomyScope,
    CircuitState,
    RuntimeGovernanceEngine,
)
from aura.cognition.scheduling.models import ScheduleStatus, ScheduleType, TemporalSchedule
from aura.cognition.scheduling.persistence import RuntimeStateStore
from aura.cognition.scheduling.runtime import ContinuousAutonomyRuntime
from aura.cognition.scheduling.store import ScheduleStore
from aura.config.manager import ConfigurationManager
from aura.container import DependencyContainer
from aura.events.bus import EventBus
from aura.memory.store import SQLiteMemoryStore


def test_01_initial_governance_engine_state():
    """Test 1: RuntimeGovernanceEngine initializes with default UNRESTRICTED scope."""
    engine = RuntimeGovernanceEngine()
    assert engine.get_scope() == AutonomyScope.UNRESTRICTED

    snap = engine.get_governance_snapshot()
    assert snap.scope == AutonomyScope.UNRESTRICTED
    assert snap.governance_enabled
    assert snap.active_circuits_count == 0
    assert snap.total_evaluations == 0


def test_02_autonomy_scope_transitions():
    """Test 2: Changing AutonomyScope emits AutonomyScopeChanged event."""
    event_bus = EventBus()
    events: list[tuple[str, str]] = []
    event_bus.subscribe(
        "AutonomyScopeChanged",
        lambda e: events.append((e.previous_scope, e.new_scope)),
    )

    engine = RuntimeGovernanceEngine(event_bus=event_bus)
    engine.set_authority_scope(AutonomyScope.READ_ONLY)
    assert engine.get_scope() == AutonomyScope.READ_ONLY

    engine.set_authority_scope(AutonomyScope.SANDBOXED)
    assert engine.get_scope() == AutonomyScope.SANDBOXED

    engine.set_authority_scope(AutonomyScope.DISABLED)
    assert engine.get_scope() == AutonomyScope.DISABLED

    assert events == [
        ("UNRESTRICTED", "READ_ONLY"),
        ("READ_ONLY", "SANDBOXED"),
        ("SANDBOXED", "DISABLED"),
    ]


def test_03_scope_disabled_blocks_all_actions():
    """Test 3: AutonomyScope.DISABLED blocks all evaluations immediately."""
    event_bus = EventBus()
    blocked_events: list[str] = []
    event_bus.subscribe(
        "GovernanceExecutionBlocked",
        lambda e: blocked_events.append(e.reason),
    )

    engine = RuntimeGovernanceEngine(event_bus=event_bus)
    engine.set_authority_scope(AutonomyScope.DISABLED)

    dec = engine.evaluate_action("sched_01", is_mutating=False)
    assert not dec.allowed
    assert dec.reason == "governance_scope_disabled"
    assert len(blocked_events) == 1


def test_04_scope_read_only_blocks_mutating_actions():
    """Test 4: AutonomyScope.READ_ONLY permits non-mutating actions, blocks mutating ones."""
    engine = RuntimeGovernanceEngine()
    engine.set_authority_scope(AutonomyScope.READ_ONLY)

    dec_read = engine.evaluate_action("sched_read", is_mutating=False)
    assert dec_read.allowed
    assert dec_read.reason == "authorized"

    dec_write = engine.evaluate_action("sched_write", is_mutating=True)
    assert not dec_write.allowed
    assert dec_write.reason == "governance_scope_read_only"


def test_05_scope_sandboxed_blocks_external_categories():
    """Test 5: AutonomyScope.SANDBOXED blocks EXTERNAL and DESTRUCTIVE categories."""
    engine = RuntimeGovernanceEngine()
    engine.set_authority_scope(AutonomyScope.SANDBOXED)

    dec_local = engine.evaluate_action("sched_local", category="LOCAL")
    assert dec_local.allowed

    dec_ext = engine.evaluate_action("sched_ext", category="EXTERNAL")
    assert not dec_ext.allowed
    assert dec_ext.reason == "governance_scope_sandboxed"

    dec_dest = engine.evaluate_action("sched_dest", category="DESTRUCTIVE")
    assert not dec_dest.allowed
    assert dec_dest.reason == "governance_scope_sandboxed"


def test_06_circuit_breaker_tripping_on_failures():
    """Test 6: Circuit breaker trips OPEN when failure threshold is reached."""
    event_bus = EventBus()
    tripped_events: list[str] = []
    event_bus.subscribe(
        "CircuitBreakerTripped",
        lambda e: tripped_events.append(e.target_id),
    )

    config = ConfigurationManager()
    config.set("autonomy.circuit_failure_threshold", 3)

    engine = RuntimeGovernanceEngine(event_bus=event_bus, config=config)

    for _ in range(2):
        engine.record_action_outcome("action_err", success=False, error="timeout")
        assert engine.get_circuit_state("action_err") == CircuitState.CLOSED

    engine.record_action_outcome("action_err", success=False, error="timeout")
    assert engine.get_circuit_state("action_err") == CircuitState.OPEN
    assert tripped_events == ["action_err"]

    dec = engine.evaluate_action("action_err")
    assert not dec.allowed
    assert dec.reason == "circuit_breaker_open"


def test_07_circuit_breaker_cooloff_and_half_open():
    """Test 7: Circuit breaker transitions to HALF_OPEN after cooloff expires."""
    clock = TestClock("2026-08-18T10:00:00+00:00")
    config = ConfigurationManager()
    config.set("autonomy.circuit_failure_threshold", 2)
    config.set("autonomy.circuit_cooloff_seconds", 10.0)

    engine = RuntimeGovernanceEngine(clock=clock, config=config)
    engine.record_action_outcome("action_cool", success=False)
    engine.record_action_outcome("action_cool", success=False)

    assert engine.get_circuit_state("action_cool") == CircuitState.OPEN

    # Evaluate before cooloff -> blocked
    dec_blocked = engine.evaluate_action("action_cool")
    assert not dec_blocked.allowed

    # Advance clock past cooloff
    clock.advance(15.0)

    dec_half = engine.evaluate_action("action_cool")
    assert dec_half.allowed
    assert dec_half.circuit_state == CircuitState.HALF_OPEN


def test_08_circuit_breaker_reset_on_success():
    """Test 8: Recording success resets OPEN/HALF_OPEN circuit breaker to CLOSED."""
    event_bus = EventBus()
    reset_events: list[str] = []
    event_bus.subscribe("CircuitBreakerReset", lambda e: reset_events.append(e.target_id))

    config = ConfigurationManager()
    config.set("autonomy.circuit_failure_threshold", 2)

    engine = RuntimeGovernanceEngine(event_bus=event_bus, config=config)
    engine.record_action_outcome("action_reset", success=False)
    engine.record_action_outcome("action_reset", success=False)
    assert engine.get_circuit_state("action_reset") == CircuitState.OPEN

    engine.record_action_outcome("action_reset", success=True)
    assert engine.get_circuit_state("action_reset") == CircuitState.CLOSED
    assert reset_events == ["action_reset"]


def test_09_manual_circuit_breaker_trip_and_reset():
    """Test 9: Manual trip_circuit and reset_circuit override circuit breaker state."""
    engine = RuntimeGovernanceEngine()
    engine.trip_circuit("target_01", reason="manual_override")
    assert engine.get_circuit_state("target_01") == CircuitState.OPEN

    dec = engine.evaluate_action("target_01")
    assert not dec.allowed

    engine.reset_circuit("target_01", reason="manual_clear")
    assert engine.get_circuit_state("target_01") == CircuitState.CLOSED

    dec_after = engine.evaluate_action("target_01")
    assert dec_after.allowed


def test_10_rate_limiting_enforcement():
    """Test 10: Rate limiter blocks calls exceeding max_calls_per_minute."""
    config = ConfigurationManager()
    config.set("autonomy.rate_limit_max_calls_per_minute", 3)

    engine = RuntimeGovernanceEngine(config=config)

    for i in range(3):
        dec = engine.evaluate_action(f"action_{i}")
        assert dec.allowed

    dec_exceeded = engine.evaluate_action("action_extra")
    assert not dec_exceeded.allowed
    assert dec_exceeded.reason == "rate_limit_exceeded"


def test_11_governance_events_publishing():
    """Test 11: All governance events are published to EventBus."""
    event_bus = EventBus()
    events_captured: list[str] = []

    event_bus.subscribe("AutonomyScopeChanged", lambda e: events_captured.append(e.__event_name__))
    event_bus.subscribe("CircuitBreakerTripped", lambda e: events_captured.append(e.__event_name__))
    event_bus.subscribe("CircuitBreakerReset", lambda e: events_captured.append(e.__event_name__))
    event_bus.subscribe(
        "GovernanceExecutionBlocked", lambda e: events_captured.append(e.__event_name__)
    )

    config = ConfigurationManager()
    config.set("autonomy.circuit_failure_threshold", 1)

    engine = RuntimeGovernanceEngine(event_bus=event_bus, config=config)
    engine.set_authority_scope(AutonomyScope.READ_ONLY)
    engine.evaluate_action("mutating_action", is_mutating=True)

    engine.record_action_outcome("action_fail", success=False)
    engine.reset_circuit("action_fail")

    assert events_captured == [
        "AutonomyScopeChanged",
        "GovernanceExecutionBlocked",
        "CircuitBreakerTripped",
        "CircuitBreakerReset",
    ]


def test_12_dispatcher_governance_integration():
    """Test 12: ScheduleDispatcher respects RuntimeGovernanceEngine decisions."""
    memory_store = SQLiteMemoryStore(db_path=":memory:")
    schedule_store = ScheduleStore(store=memory_store)
    goal_mgr = GoalManager(store=GoalStore(store=memory_store))
    goal = goal_mgr.create_goal("Test governance goal")

    engine = RuntimeGovernanceEngine()
    engine.set_authority_scope(AutonomyScope.DISABLED)

    dispatcher = ScheduleDispatcher(
        schedule_store=schedule_store,
        goal_manager=goal_mgr,
        governance_engine=engine,
    )

    sched = TemporalSchedule(
        schedule_id="sched_gov_test",
        goal_id=goal.goal_id,
        schedule_type=ScheduleType.INTERVAL,
        expression="30s",
        status=ScheduleStatus.ACTIVE,
    )
    schedule_store.save_schedule(sched)

    results = dispatcher.process_due_schedules(at_timestamp="2026-08-18T10:00:00+00:00")
    assert len(results) == 1
    assert not results[0].dispatched
    assert "Governance blocked execution" in results[0].reason


def test_13_control_plane_governance_integration():
    """Test 13: RuntimeControlPlane manages governance scope and snapshot."""
    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=GoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher)

    engine = RuntimeGovernanceEngine()
    control_plane = RuntimeControlPlane(runtime=runtime, governance_engine=engine)

    control_plane.set_governance_scope(AutonomyScope.READ_ONLY)
    assert engine.get_scope() == AutonomyScope.READ_ONLY

    snap = control_plane.get_governance_snapshot()
    assert snap is not None
    assert snap.scope == AutonomyScope.READ_ONLY


def test_14_autonomy_module_governance_integration():
    """Test 14: AutonomyModule wires RuntimeGovernanceEngine into dispatcher and control plane."""
    clock = TestClock("2026-08-18T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=GoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    engine = RuntimeGovernanceEngine(clock=clock)
    module = AutonomyModule(clock=clock, runtime=runtime, governance_engine=engine)
    module.on_initialize()

    assert module.governance_engine is engine
    assert module.schedule_dispatcher.governance_engine is engine
    assert module.control_plane is not None
    assert module.control_plane.governance_engine is engine

    snap = module.get_governance_snapshot()
    assert snap is not None
    assert snap.scope == AutonomyScope.UNRESTRICTED


def test_15_ioc_container_governance_registration():
    """Test 15: DependencyContainer registers and resolves RuntimeGovernanceEngine."""
    container = DependencyContainer()
    engine = RuntimeGovernanceEngine()
    container.register(RuntimeGovernanceEngine, instance=engine)

    resolved = container.resolve(RuntimeGovernanceEngine)
    assert resolved is engine


def test_16_multithreaded_concurrent_governance_evaluations():
    """Test 16: Thread safety under high concurrency."""
    engine = RuntimeGovernanceEngine()
    errors: list[Exception] = []

    def worker(idx: int):
        try:
            for _ in range(5):
                engine.evaluate_action(f"action_{idx}")
                engine.record_action_outcome(f"action_{idx}", success=(idx % 2 == 0))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    assert len(errors) == 0
    snap = engine.get_governance_snapshot()
    assert snap.total_evaluations == 50


def test_17_disabled_governance_bypass_safety():
    """Test 17: Disabling governance permits all actions cleanly."""
    config = ConfigurationManager()
    config.set("autonomy.governance_enabled", False)

    engine = RuntimeGovernanceEngine(config=config)
    engine.set_authority_scope(AutonomyScope.DISABLED)

    dec = engine.evaluate_action("sched_bypass")
    assert dec.allowed
    assert dec.reason == "governance_disabled"


def test_18_bypass_prevention_on_internal_methods():
    """Test 18: Direct method invocation cannot bypass DISABLED scope."""
    engine = RuntimeGovernanceEngine()
    engine.set_authority_scope(AutonomyScope.DISABLED)

    dec = engine.evaluate_action("target_action", is_mutating=False, category="READ")
    assert not dec.allowed
    assert dec.reason == "governance_scope_disabled"


def test_19_stage1_to_stage9_compatibility():
    """Test 19: Full compatibility with Stage 1-9 persistence, recovery and control plane."""
    clock = TestClock("2026-08-18T10:00:00+00:00")
    memory_store = SQLiteMemoryStore(db_path=":memory:")
    state_store = RuntimeStateStore(store=memory_store)
    engine = RuntimeGovernanceEngine(clock=clock)

    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=GoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    module = AutonomyModule(
        clock=clock,
        runtime=runtime,
        state_store=state_store,
        governance_engine=engine,
    )
    module.on_initialize()
    module.on_start()

    try:
        loaded = state_store.load_snapshot("AuraAutonomyRuntime")
        assert loaded is not None
        assert loaded.operational_state == "RUNNING"
        assert module.get_governance_snapshot() is not None
    finally:
        module.on_stop()


def test_20_governance_diagnostics_snapshot_immutability():
    """Test 20: GovernanceStatusSnapshot is immutable."""
    engine = RuntimeGovernanceEngine()
    snap = engine.get_governance_snapshot()

    try:
        snap.allowed_evaluations = 999  # type: ignore[misc]
        raise AssertionError("Should have raised AttributeError")
    except AttributeError:
        pass
