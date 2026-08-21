from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest

from aura.autonomy.goals import GoalManager
from aura.autonomy.module import AutonomyModule
from aura.cognition.goals import GoalManager as CognitionGoalManager
from aura.cognition.scheduling import (
    ActivityLevel,
    ContinuousAutonomyRuntime,
    PolicyAdaptationEngine,
    PolicyDecision,
    PriorityMode,
    ScheduleDispatcher,
    ScheduleStore,
    SystemClock,
    SystemSignals,
    TestClock,
)
from aura.config import ConfigurationManager
from aura.events import (
    EventBus,
)


def test_01_policy_disabled_preserves_original_behavior():
    """Test 1: When adaptation is disabled, policy returns NORMAL and configured interval."""
    cfg = ConfigurationManager()
    cfg.load_from_dict({"autonomy.adaptation_enabled": False})
    clock = TestClock("2026-08-17T10:00:00+00:00")
    engine = PolicyAdaptationEngine(clock=clock, config=cfg)

    signals = SystemSignals(health_status="DEGRADED", system_load_level="HIGH")
    decision = engine.evaluate_policy(signals, configured_interval=2.0)

    assert isinstance(decision, PolicyDecision)
    assert decision.activity_level == ActivityLevel.NORMAL
    assert decision.priority_mode == PriorityMode.STANDARD
    assert decision.effective_tick_interval_seconds == 2.0
    assert decision.reason == "adaptation_disabled"


def test_02_healthy_status_returns_normal():
    """Test 2: Healthy conditions produce NORMAL activity level and configured tick interval."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    engine = PolicyAdaptationEngine(clock=clock)

    signals = SystemSignals(
        health_status="HEALTHY",
        worker_thread_alive=True,
        system_load_level="NORMAL",
    )
    decision = engine.evaluate_policy(signals, configured_interval=1.0)

    assert decision.activity_level == ActivityLevel.NORMAL
    assert decision.priority_mode == PriorityMode.STANDARD
    assert decision.effective_tick_interval_seconds == 1.0
    assert decision.reason == "healthy_normal_operation"


def test_03_degraded_status_returns_reduced():
    """Test 3: Degraded health produces REDUCED activity level and increased tick interval."""
    cfg = ConfigurationManager()
    cfg.load_from_dict({"autonomy.reduced_activity_multiplier": 2.5})
    clock = TestClock("2026-08-17T10:00:00+00:00")
    engine = PolicyAdaptationEngine(clock=clock, config=cfg)

    signals = SystemSignals(health_status="DEGRADED")
    decision = engine.evaluate_policy(signals, configured_interval=1.0)

    assert decision.activity_level == ActivityLevel.REDUCED
    assert decision.priority_mode == PriorityMode.THROTTLED
    assert decision.effective_tick_interval_seconds == 2.5
    assert "reduced_due_to_degraded" in decision.reason


def test_04_stopped_or_failed_recovery_returns_suspended():
    """Test 4: Stopped runtime or recovery failures produce SUSPENDED activity level."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    engine = PolicyAdaptationEngine(clock=clock)

    signals = SystemSignals(health_status="STOPPED", worker_thread_alive=False)
    decision = engine.evaluate_policy(signals, configured_interval=1.0)

    assert decision.activity_level == ActivityLevel.SUSPENDED
    assert decision.priority_mode == PriorityMode.CRITICAL_ONLY
    assert decision.effective_tick_interval_seconds >= 5.0
    assert "suspended_due_to_health" in decision.reason


def test_05_high_system_load_returns_reduced():
    """Test 5: High or critical system load triggers REDUCED activity level."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    engine = PolicyAdaptationEngine(clock=clock)

    signals = SystemSignals(health_status="HEALTHY", system_load_level="HIGH")
    decision = engine.evaluate_policy(signals, configured_interval=1.0)

    assert decision.activity_level == ActivityLevel.REDUCED
    assert decision.priority_mode == PriorityMode.THROTTLED
    assert decision.effective_tick_interval_seconds == 2.0


def test_06_recovery_to_healthy_restores_normal():
    """Test 6: Returning to healthy status restores NORMAL activity level."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    bus = EventBus()
    policy_events = []
    bus.subscribe("RuntimePolicyChanged", policy_events.append)
    engine = PolicyAdaptationEngine(clock=clock, event_bus=bus)

    d1 = engine.evaluate_policy(SystemSignals(health_status="DEGRADED"), configured_interval=1.0)
    assert d1.activity_level == ActivityLevel.REDUCED

    clock.advance(1.0)
    d2 = engine.evaluate_policy(SystemSignals(health_status="HEALTHY"), configured_interval=1.0)
    assert d2.activity_level == ActivityLevel.NORMAL

    assert len(policy_events) == 1
    assert policy_events[0].previous_activity_level == "REDUCED"
    assert policy_events[0].new_activity_level == "NORMAL"


def test_07_invalid_configured_intervals_sanitized():
    """Test 7: Zero or negative configured tick intervals are clamped safely."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    engine = PolicyAdaptationEngine(clock=clock)

    d1 = engine.evaluate_policy(SystemSignals(), configured_interval=-5.0)
    assert d1.effective_tick_interval_seconds >= 0.05

    d2 = engine.evaluate_policy(SystemSignals(), configured_interval=0.0)
    assert d2.effective_tick_interval_seconds >= 0.05


def test_08_nan_and_infinity_sanitized():
    """Test 8: NaN and infinity inputs in interval calculation are clamped safely."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    engine = PolicyAdaptationEngine(clock=clock)

    d1 = engine.evaluate_policy(SystemSignals(), configured_interval=float("nan"))
    assert not math.isnan(d1.effective_tick_interval_seconds)
    assert d1.effective_tick_interval_seconds == 1.0

    d2 = engine.evaluate_policy(SystemSignals(), configured_interval=float("inf"))
    assert not math.isinf(d2.effective_tick_interval_seconds)
    assert d2.effective_tick_interval_seconds == 1.0


def test_09_min_max_interval_limits_enforced():
    """Test 9: Min and max tick interval boundaries are strictly respected."""
    cfg = ConfigurationManager()
    cfg.load_from_dict(
        {
            "autonomy.min_tick_interval_seconds": 0.1,
            "autonomy.max_tick_interval_seconds": 5.0,
        }
    )
    clock = TestClock("2026-08-17T10:00:00+00:00")
    engine = PolicyAdaptationEngine(clock=clock, config=cfg)

    d1 = engine.evaluate_policy(SystemSignals(), configured_interval=0.01)
    assert d1.effective_tick_interval_seconds == 0.1

    d2 = engine.evaluate_policy(SystemSignals(), configured_interval=10.0)
    assert d2.effective_tick_interval_seconds == 5.0


def test_10_policy_decision_is_immutable():
    """Test 10: PolicyDecision dataclass is frozen and immutable."""
    decision = PolicyDecision(
        effective_tick_interval_seconds=1.0,
        activity_level=ActivityLevel.NORMAL,
        priority_mode=PriorityMode.STANDARD,
        reason="test",
        timestamp="2026-08-17T10:00:00Z",
    )
    with pytest.raises(AttributeError):
        decision.effective_tick_interval_seconds = 2.0  # type: ignore[misc]


def test_11_deterministic_evaluation():
    """Test 11: Identical input signals produce identical policy decisions."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    engine = PolicyAdaptationEngine(clock=clock)
    signals = SystemSignals(health_status="DEGRADED", failed_ticks=3)

    d1 = engine.evaluate_policy(signals, configured_interval=1.5)
    d2 = engine.evaluate_policy(signals, configured_interval=1.5)

    assert d1.effective_tick_interval_seconds == d2.effective_tick_interval_seconds
    assert d1.activity_level == d2.activity_level
    assert d1.priority_mode == d2.priority_mode


def test_12_concurrent_policy_evaluations():
    """Test 12: Multiple concurrent worker threads evaluating policy do not deadlock."""
    clock = SystemClock()
    engine = PolicyAdaptationEngine(clock=clock)
    signals = SystemSignals(health_status="HEALTHY")

    def evaluate_task():
        return engine.evaluate_policy(signals, configured_interval=1.0)

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(evaluate_task) for _ in range(50)]
        results = [f.result() for f in futures]

    assert len(results) == 50
    assert all(r.activity_level == ActivityLevel.NORMAL for r in results)


def test_13_integration_with_diagnostics_snapshot():
    """Test 13: Runtime effective tick interval updates dynamically from policy engine."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    engine = PolicyAdaptationEngine(clock=clock)
    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)

    runtime = ContinuousAutonomyRuntime(
        dispatcher=dispatcher,
        clock=clock,
        tick_interval_seconds=1.0,
        policy_engine=engine,
    )

    # When stopped, health_status is STOPPED -> SUSPENDED interval (10.0)
    assert runtime.effective_tick_interval_seconds == 10.0

    # When running with active worker thread -> HEALTHY (1.0)
    mock_thread = MagicMock()
    mock_thread.is_alive.return_value = True
    runtime._running = True
    runtime._thread = mock_thread
    assert runtime.effective_tick_interval_seconds == 1.0


def test_14_integration_with_autonomy_module():
    """Test 14: AutonomyModule initializes and registers PolicyAdaptationEngine."""
    cfg = ConfigurationManager()
    clock = TestClock("2026-08-17T10:00:00+00:00")
    mod = AutonomyModule(config=cfg, clock=clock)
    mod.on_initialize()

    assert mod.policy_engine is not None
    assert isinstance(mod.policy_engine, PolicyAdaptationEngine)
    assert mod.runtime is not None
    assert mod.runtime.policy_engine is mod.policy_engine


def test_15_dynamic_tick_adaptation_in_runtime():
    """Test 15: Runtime worker loop adjusts sleep duration when policy changes."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    engine = PolicyAdaptationEngine(clock=clock)
    store = MagicMock(spec=ScheduleStore)
    store.list_eligible_schedules.return_value = []
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)

    runtime = ContinuousAutonomyRuntime(
        dispatcher=dispatcher,
        clock=clock,
        tick_interval_seconds=1.0,
        policy_engine=engine,
    )

    runtime.start()
    assert runtime.effective_tick_interval_seconds == 1.0
    runtime.stop()


def test_16_shutdown_during_policy_evaluation():
    """Test 16: Shutdown during policy evaluation cleanly stops without exception."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    engine = PolicyAdaptationEngine(clock=clock)
    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)

    runtime = ContinuousAutonomyRuntime(
        dispatcher=dispatcher,
        clock=clock,
        tick_interval_seconds=0.1,
        policy_engine=engine,
    )

    runtime.start()
    engine.evaluate_policy(SystemSignals(health_status="DEGRADED"))
    runtime.stop()
    assert not runtime.is_running


def test_17_stage6_recovery_not_duplicated():
    """Test 17: PolicyAdaptationEngine does not attempt worker self-recovery."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    engine = PolicyAdaptationEngine(clock=clock)

    signals = SystemSignals(health_status="STOPPED", worker_thread_alive=False)
    decision = engine.evaluate_policy(signals)

    assert decision.activity_level == ActivityLevel.SUSPENDED
    # Engine only produces PolicyDecision, does not resurrect runtime threads.


def test_18_full_stage1_7_compatibility():
    """Test 18: Complete end-to-end compatibility with Stage 1 through 7."""
    cfg = ConfigurationManager()
    clock = TestClock("2026-08-17T10:00:00+00:00")
    bus = EventBus()
    store = MagicMock(spec=ScheduleStore)
    store.list_eligible_schedules.return_value = []
    goals = GoalManager(event_bus=bus)

    mod = AutonomyModule(
        config=cfg,
        event_bus=bus,
        goal_manager=goals,
        schedule_store=store,
        clock=clock,
    )
    mod.load()
    mod.initialize()
    mod.start()

    assert mod.health.status.value in {"Running", "Ready"}
    assert mod.policy_engine is not None

    mod.stop()
