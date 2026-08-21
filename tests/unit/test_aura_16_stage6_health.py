from __future__ import annotations

import threading
from unittest.mock import MagicMock

from aura.autonomy.module import AutonomyModule
from aura.cognition.goals import GoalManager as CognitionGoalManager
from aura.cognition.scheduling import (
    ContinuousAutonomyRuntime,
    ScheduleDispatcher,
    ScheduleStore,
    TestClock,
)
from aura.config import ConfigurationManager
from aura.core.aura import AURA, AURABootOptions
from aura.events import (
    EventBus,
    RuntimeHealthChanged,
    RuntimeRecovered,
    RuntimeRecoveryAttempted,
    RuntimeRecoveryFailed,
)
from aura.modules.base import ModuleStatus


def test_01_initial_metrics():
    """Test 1: Initial metrics snapshot has default zero/None values."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    snapshot = runtime.get_metrics_snapshot()
    assert snapshot.runtime_name == "AuraAutonomyRuntime"
    assert not snapshot.is_running
    assert not snapshot.worker_thread_alive
    assert snapshot.tick_count == 0
    assert snapshot.successful_ticks == 0
    assert snapshot.failed_ticks == 0
    assert snapshot.skipped_overlapping_ticks == 0
    assert snapshot.last_tick_at is None
    assert snapshot.last_successful_tick_at is None
    assert snapshot.last_failed_tick_at is None
    assert snapshot.last_error is None
    assert snapshot.started_at is None
    assert snapshot.uptime_seconds == 0.0


def test_02_successful_tick_updates_metrics():
    """Test 2: Successful tick updates tick_count, successful_ticks, and last_successful_tick_at."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    store.list_eligible_schedules.return_value = []
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    runtime.tick()

    snapshot = runtime.get_metrics_snapshot()
    assert snapshot.tick_count == 1
    assert snapshot.successful_ticks == 1
    assert snapshot.failed_ticks == 0
    assert snapshot.last_tick_at == "2026-08-17T10:00:00+00:00"
    assert snapshot.last_successful_tick_at == "2026-08-17T10:00:00+00:00"


def test_03_failed_tick_updates_metrics():
    """Test 3: Exception during tick updates failed_ticks, last_failed_tick_at, and last_error."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    store.list_eligible_schedules.side_effect = RuntimeError("Database connection lost")
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    runtime.tick()

    snapshot = runtime.get_metrics_snapshot()
    assert snapshot.tick_count == 1
    assert snapshot.successful_ticks == 0
    assert snapshot.failed_ticks == 1
    assert snapshot.last_tick_at == "2026-08-17T10:00:00+00:00"
    assert snapshot.last_failed_tick_at == "2026-08-17T10:00:00+00:00"
    assert "Database connection lost" in str(snapshot.last_error)


def test_04_overlapping_tick_increments_skipped_metric():
    """Test 4: Overlapping tick when tick_lock is acquired increments skipped_overlapping_ticks."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    acquired = threading.Event()
    release = threading.Event()

    def lock_holder():
        runtime._tick_lock.acquire()
        acquired.set()
        release.wait()
        runtime._tick_lock.release()

    t = threading.Thread(target=lock_holder, daemon=True)
    t.start()
    acquired.wait()

    try:
        results = runtime.tick()
        assert results == []
    finally:
        release.set()
        t.join()

    snapshot = runtime.get_metrics_snapshot()
    assert snapshot.skipped_overlapping_ticks == 1


def test_05_worker_alive_reports_correct_state():
    """Test 5: Worker thread alive reports True when runtime is started."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    store.list_eligible_schedules.return_value = []
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(
        dispatcher=dispatcher, clock=clock, tick_interval_seconds=0.1
    )

    runtime.start()
    try:
        assert runtime.is_running
        snapshot = runtime.get_metrics_snapshot()
        assert snapshot.worker_thread_alive
        assert snapshot.is_running
    finally:
        runtime.stop()

    assert not runtime.is_running


def test_06_worker_dead_detected():
    """Test 6: Detecting when worker thread is dead while runtime is_running=True."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    runtime._running = True  # Simulate running state without active thread
    snapshot = runtime.get_metrics_snapshot()
    assert snapshot.is_running
    assert not snapshot.worker_thread_alive


def test_07_health_check_healthy():
    """Test 7: on_health_check returns healthy metrics when worker thread is alive."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    store.list_eligible_schedules.return_value = []
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(
        dispatcher=dispatcher, clock=clock, tick_interval_seconds=0.1
    )
    mod = AutonomyModule(runtime=runtime, clock=clock)

    runtime.start()
    try:
        health_metrics = mod.on_health_check()
        assert health_metrics["worker_thread_alive"] is True
        assert health_metrics["is_running"] is True
        assert mod.health.status in {
            ModuleStatus.RUNNING,
            ModuleStatus.READY,
            ModuleStatus.UNLOADED,
        }
    finally:
        runtime.stop()


def test_08_health_check_degraded():
    """Test 8: on_health_check detects dead worker thread and updates health status to DEGRADED."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    cfg = ConfigurationManager()
    cfg.load_from_dict(
        {
            "autonomy.health_monitoring_enabled": True,
            "autonomy.self_recovery_enabled": False,  # Disable auto-recovery to test DEGRADED state
        }
    )
    mod = AutonomyModule(config=cfg, runtime=runtime, clock=clock)

    runtime._running = True  # Simulate dead thread while running
    mod.on_health_check()

    assert mod.health.status == ModuleStatus.DEGRADED
    assert mod.health.last_error == "worker_thread_dead"


def test_09_self_recovery_restarts_worker():
    """Test 9: Self-recovery restarts worker thread and returns True."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    store.list_eligible_schedules.return_value = []
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(
        dispatcher=dispatcher, clock=clock, tick_interval_seconds=0.1
    )

    runtime._running = True  # Dead worker state
    success = runtime.recover(reason="unit_test")
    try:
        assert success
        assert runtime.is_running
        snapshot = runtime.get_metrics_snapshot()
        assert snapshot.worker_thread_alive
    finally:
        runtime.stop()


def test_10_self_recovery_prevents_duplicate_workers():
    """Test 10: Calling recover on an alive worker thread does not spawn duplicate workers."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    store.list_eligible_schedules.return_value = []
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(
        dispatcher=dispatcher, clock=clock, tick_interval_seconds=0.1
    )

    runtime.start()
    old_thread = runtime._thread
    try:
        success = runtime.recover(reason="unit_test")
        assert success is True
        new_thread = runtime._thread
        assert new_thread is old_thread
    finally:
        runtime.stop()


def test_11_recovery_idempotent():
    """Test 11: Sequential recovery calls execute cleanly without deadlocks or errors."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    store.list_eligible_schedules.return_value = []
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(
        dispatcher=dispatcher, clock=clock, tick_interval_seconds=0.1
    )

    runtime._running = True  # Dead worker state
    try:
        res1 = runtime.recover(reason="test1")
        res2 = runtime.recover(reason="test2")
        assert res1 is True
        assert res2 is True
    finally:
        runtime.stop()


def test_12_recovery_failure_recorded():
    """Test 12: Exceeding max_attempts limit emits RuntimeRecoveryFailed event and returns False."""
    bus = EventBus()
    events = []
    bus.subscribe("RuntimeRecoveryFailed", events.append)

    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(
        dispatcher=dispatcher, clock=clock, event_bus=bus, tick_interval_seconds=0.1
    )

    runtime._running = True  # Dead worker state
    try:
        res1 = runtime.recover(reason="r1", max_attempts=2, backoff_seconds=60.0)
        runtime._thread = None  # Simulate dead thread again
        res2 = runtime.recover(reason="r2", max_attempts=2, backoff_seconds=60.0)
        runtime._thread = None  # Simulate dead thread again
        res3 = runtime.recover(reason="r3", max_attempts=2, backoff_seconds=60.0)

        assert res1 is True
        assert res2 is True
        assert res3 is False  # 3rd attempt exceeds max_attempts=2
        assert len(events) == 1
        assert isinstance(events[0], RuntimeRecoveryFailed)
    finally:
        runtime.stop()


def test_13_recovery_max_attempts_limit():
    """Test 13: Anti-recovery storm enforces max_attempts limit within backoff window."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(
        dispatcher=dispatcher, clock=clock, tick_interval_seconds=0.1
    )

    runtime._running = True  # Dead worker state
    try:
        assert runtime.recover(max_attempts=1, backoff_seconds=30.0) is True
        runtime._thread = None  # Simulate dead thread again
        assert runtime.recover(max_attempts=1, backoff_seconds=30.0) is False
    finally:
        runtime.stop()


def test_14_recovery_backoff_window():
    """Test 14: Advancing clock beyond backoff_seconds window resets attempt counter."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(
        dispatcher=dispatcher, clock=clock, tick_interval_seconds=0.1
    )

    runtime._running = True  # Dead worker state
    try:
        assert runtime.recover(max_attempts=1, backoff_seconds=10.0) is True
        runtime._thread = None  # Simulate dead thread again
        assert runtime.recover(max_attempts=1, backoff_seconds=10.0) is False

        clock.advance(seconds=15)  # Advance clock past backoff window
        runtime._thread = None  # Simulate dead thread again
        assert runtime.recover(max_attempts=1, backoff_seconds=10.0) is True
    finally:
        runtime.stop()


def test_15_configuration_flags_disable_recovery():
    """Test 15: autonomy.self_recovery_enabled=False prevents auto-recovery."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    cfg = ConfigurationManager()
    cfg.load_from_dict(
        {
            "autonomy.health_monitoring_enabled": True,
            "autonomy.self_recovery_enabled": False,
        }
    )
    mod = AutonomyModule(config=cfg, runtime=runtime, clock=clock)

    runtime._running = True  # Dead thread simulation
    mod.on_health_check()

    assert mod.health.status == ModuleStatus.DEGRADED
    assert not runtime._thread  # Worker thread was NOT restarted


def test_16_shutdown_cleans_up_runtime():
    """Test 16: Module/runtime shutdown cleanly joins thread and clears running state."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    store.list_eligible_schedules.return_value = []
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(
        dispatcher=dispatcher, clock=clock, tick_interval_seconds=0.1
    )
    mod = AutonomyModule(runtime=runtime, clock=clock)

    runtime.start()
    assert runtime.is_running
    mod.on_stop()
    assert not runtime.is_running


def test_17_health_and_recovery_events_published():
    """Test 17: RuntimeHealthChanged and recovery events are published to EventBus."""
    bus = EventBus()
    health_events = []
    attempt_events = []
    recovered_events = []

    bus.subscribe("RuntimeHealthChanged", health_events.append)
    bus.subscribe("RuntimeRecoveryAttempted", attempt_events.append)
    bus.subscribe("RuntimeRecovered", recovered_events.append)

    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    store.list_eligible_schedules.return_value = []
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(
        dispatcher=dispatcher, clock=clock, event_bus=bus, tick_interval_seconds=0.1
    )

    cfg = ConfigurationManager()
    cfg.load_from_dict(
        {
            "autonomy.health_monitoring_enabled": True,
            "autonomy.self_recovery_enabled": True,
        }
    )
    mod = AutonomyModule(config=cfg, container=None, event_bus=bus, runtime=runtime, clock=clock)

    runtime._running = True  # Simulate dead thread while running
    try:
        mod.on_health_check()

        assert len(health_events) == 1
        assert isinstance(health_events[0], RuntimeHealthChanged)
        assert len(attempt_events) == 1
        assert isinstance(attempt_events[0], RuntimeRecoveryAttempted)
        assert len(recovered_events) == 1
        assert isinstance(recovered_events[0], RuntimeRecovered)
    finally:
        runtime.stop()


def test_18_stage5_compatibility():
    """Test 18: Full E2E boot and shutdown with health monitoring and recovery enabled."""
    cfg = ConfigurationManager()
    cfg.load_from_dict(
        {
            "autonomy.health_monitoring_enabled": True,
            "autonomy.self_recovery_enabled": True,
        }
    )

    opts = AURABootOptions(enable_scheduler=False, enable_health_monitor=False)
    aura = AURA(options=opts, config=cfg)
    aura.boot()

    mod = aura.module_manager.get("autonomy") if aura.module_manager else None
    assert isinstance(mod, AutonomyModule)
    assert mod.runtime is not None
    assert mod.runtime.is_running

    # Perform health check via module
    metrics = mod.on_health_check()
    assert metrics["worker_thread_alive"] is True
    assert metrics["is_running"] is True

    aura.shutdown(wait=True)
    assert not mod.runtime.is_running


def test_19_recover_on_stopped_runtime_returns_false():
    """Test 19: recover() on a legally stopped runtime returns False without creating a thread."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(
        dispatcher=dispatcher, clock=clock, tick_interval_seconds=0.1
    )

    runtime.start()
    assert runtime.is_running
    runtime.stop()
    assert not runtime.is_running

    res = runtime.recover(reason="manual_call_on_stopped_runtime")
    assert res is False
    assert not runtime.is_running
    assert runtime._thread is None


def test_20_concurrent_recover_calls():
    """Test 20: Concurrent calls to recover spawn exactly one worker thread."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    store.list_eligible_schedules.return_value = []
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(
        dispatcher=dispatcher, clock=clock, tick_interval_seconds=0.1
    )

    runtime._running = True  # Simulate dead worker state
    results = []

    def call_recover():
        res = runtime.recover(reason="concurrent_test", max_attempts=3, backoff_seconds=30.0)
        results.append(res)

    threads = [threading.Thread(target=call_recover) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    try:
        assert all(results)
        snapshot = runtime.get_metrics_snapshot()
        assert snapshot.is_running
        assert snapshot.worker_thread_alive
        assert len(runtime._recovery_attempts) == 1
    finally:
        runtime.stop()

    assert not runtime.is_running
