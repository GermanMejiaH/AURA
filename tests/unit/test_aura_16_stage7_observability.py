from __future__ import annotations

import threading
from unittest.mock import MagicMock

import pytest

from aura.autonomy.module import AutonomyModule
from aura.cognition.goals import GoalManager as CognitionGoalManager
from aura.cognition.scheduling import (
    ContinuousAutonomyRuntime,
    RuntimeDiagnostics,
    RuntimeDiagnosticsSnapshot,
    RuntimeTelemetrySnapshot,
    ScheduleDispatcher,
    ScheduleStore,
    TestClock,
)
from aura.config import ConfigurationManager
from aura.events import EventBus


def test_01_initial_snapshot():
    """Test 1: Initial unstarted snapshot returns clean default state."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    snap = runtime.get_diagnostics_snapshot()
    assert snap.tick_count == 0
    assert snap.successful_ticks == 0
    assert snap.failed_ticks == 0
    assert snap.skipped_overlapping_ticks == 0
    assert snap.started_at is None
    assert snap.last_tick_at is None
    assert snap.last_error is None
    assert snap.uptime_seconds == 0.0


def test_02_snapshot_stopped_runtime():
    """Test 2: get_diagnostics_snapshot on stopped runtime returns health=STOPPED."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    snapshot = runtime.get_diagnostics_snapshot()
    assert isinstance(snapshot, RuntimeDiagnosticsSnapshot)
    assert snapshot.runtime_name == "AuraAutonomyRuntime"
    assert not snapshot.is_running
    assert not snapshot.worker_thread_alive
    assert snapshot.thread_name is None
    assert snapshot.health_status == "STOPPED"


def test_03_snapshot_running_runtime():
    """Test 3: get_diagnostics_snapshot on running runtime returns health=HEALTHY."""
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
        snapshot = runtime.get_diagnostics_snapshot()
        assert snapshot.is_running
        assert snapshot.worker_thread_alive
        assert snapshot.thread_name == "AuraAutonomyRuntime"
        assert snapshot.health_status == "HEALTHY"
        assert snapshot.started_at == "2026-08-17T10:00:00+00:00"
    finally:
        runtime.stop()


def test_04_tick_count_tracking():
    """Test 4: Tick counts increments properly on manual tick execution."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    store.list_eligible_schedules.return_value = []
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    runtime.tick()
    runtime.tick()

    snap = runtime.get_diagnostics_snapshot()
    assert snap.tick_count == 2


def test_05_successful_ticks_count():
    """Test 5: Successful ticks count accurately recorded in telemetry."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    store.list_eligible_schedules.return_value = []
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    runtime.tick()

    snap = runtime.get_telemetry_snapshot()
    assert isinstance(snap, RuntimeTelemetrySnapshot)
    assert snap.successful_ticks == 1
    assert snap.failed_ticks == 0


def test_06_failed_ticks_count():
    """Test 6: Failed ticks count accurately recorded when dispatcher fails."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    store.list_eligible_schedules.side_effect = RuntimeError("Store error")
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    try:
        runtime.tick()
    except Exception:
        pass

    snap = runtime.get_telemetry_snapshot()
    assert snap.failed_ticks == 1
    assert snap.last_error is not None


def test_07_skipped_overlapping_ticks_count():
    """Test 7: Skipped overlapping ticks count recorded when lock is held by another thread."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    lock_acquired = threading.Event()
    release_lock = threading.Event()

    def lock_holder():
        with runtime._tick_lock:
            lock_acquired.set()
            release_lock.wait(timeout=2.0)

    t = threading.Thread(target=lock_holder)
    t.start()
    lock_acquired.wait(timeout=2.0)

    try:
        runtime.tick()
    finally:
        release_lock.set()
        t.join(timeout=2.0)

    snap = runtime.get_diagnostics_snapshot()
    assert snap.skipped_overlapping_ticks == 1


def test_08_timestamps_tracking():
    """Test 8: Last tick, successful tick, and failed tick timestamps updated."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    store.list_eligible_schedules.return_value = []
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    runtime.tick()

    snap = runtime.get_diagnostics_snapshot()
    assert snap.last_tick_at == "2026-08-17T10:00:00+00:00"
    assert snap.last_successful_tick_at == "2026-08-17T10:00:00+00:00"


def test_09_last_error_recording():
    """Test 9: Exception in tick populates last_error string."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    store.list_eligible_schedules.side_effect = ValueError("Invalid query")
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    try:
        runtime.tick()
    except Exception:
        pass

    snap = runtime.get_diagnostics_snapshot()
    assert "Invalid query" in str(snap.last_error)


def test_10_uptime_deterministic_with_test_clock():
    """Test 10: Uptime is computed deterministically using TestClock."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    runtime.start()
    try:
        clock.advance(15.0)
        snap = runtime.get_diagnostics_snapshot()
        assert snap.uptime_seconds == 15.0
    finally:
        runtime.stop()


def test_11_recovery_attempts_count():
    """Test 11: recovery_attempts counter in telemetry increments on recover()."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    store.list_eligible_schedules.return_value = []
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    runtime.start()
    runtime._running = True  # Simulate thread death
    runtime._thread = None
    runtime.recover(reason="thread_lost")
    runtime.stop()

    snap = runtime.get_telemetry_snapshot()
    assert snap.recovery_attempts >= 1


def test_12_successful_recoveries_count():
    """Test 12: successful_recoveries accurately computed in telemetry."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    store.list_eligible_schedules.return_value = []
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    runtime.start()
    runtime._running = True
    runtime._thread = None
    runtime.recover(reason="thread_lost")
    runtime.stop()

    snap = runtime.get_telemetry_snapshot()
    assert snap.successful_recoveries >= 1
    assert snap.failed_recoveries == 0


def test_13_failed_recoveries_count():
    """Test 13: Exceeding max attempts increments failed_recoveries."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    runtime.start()
    runtime._running = True
    runtime._thread = None

    # First attempt succeeds
    runtime.recover(reason="r1", max_attempts=1, backoff_seconds=100.0)

    # Simulate thread dying again
    runtime._running = True
    runtime._thread = None

    # Second attempt within backoff window fails budget
    clock.advance(10.0)
    res = runtime.recover(reason="r2", max_attempts=1, backoff_seconds=100.0)
    assert not res
    runtime.stop()

    snap = runtime.get_telemetry_snapshot()
    assert snap.failed_recoveries >= 1


def test_14_last_recovery_timestamp():
    """Test 14: last_recovery_at timestamp recorded accurately."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    store.list_eligible_schedules.return_value = []
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    runtime.start()
    runtime._running = True
    runtime._thread = None
    runtime.recover(reason="test")
    runtime.stop()

    snap = runtime.get_telemetry_snapshot()
    assert snap.last_recovery_at == "2026-08-17T10:00:00+00:00"


def test_15_health_status_derivation():
    """Test 15: health_status returns DEGRADED when thread is dead while running."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    runtime._running = True
    runtime._thread = None

    snap = runtime.get_diagnostics_snapshot()
    assert snap.health_status == "DEGRADED"


def test_16_degradation_reason_tracking():
    """Test 16: last_state_change_reason captures reason for degradation."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    store.list_eligible_schedules.return_value = []
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    runtime.start()
    runtime._running = True
    runtime._thread = None
    runtime.recover(reason="worker_thread_dead")

    snap = runtime.get_diagnostics_snapshot()
    assert snap.last_state_change_reason in {"recovered", "recovering:worker_thread_dead"}
    runtime.stop()


def test_17_snapshot_immutability():
    """Test 17: RuntimeTelemetrySnapshot and RuntimeDiagnosticsSnapshot are frozen."""
    snap1 = RuntimeTelemetrySnapshot(
        runtime_name="R1",
        is_running=False,
        thread_alive=False,
        tick_count=0,
        successful_ticks=0,
        failed_ticks=0,
        skipped_overlapping_ticks=0,
        last_tick_at=None,
        last_successful_tick_at=None,
        last_failed_tick_at=None,
        last_error=None,
        started_at=None,
        uptime_seconds=0.0,
        recovery_attempts=0,
        successful_recoveries=0,
        failed_recoveries=0,
        last_recovery_at=None,
        current_health_status="STOPPED",
        current_degradation_reason=None,
    )
    with pytest.raises(AttributeError):
        snap1.tick_count = 10  # type: ignore[misc]


def test_18_concurrent_telemetry_reads():
    """Test 18: Concurrent readers requesting telemetry snapshot run safely."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    store.list_eligible_schedules.return_value = []
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(
        dispatcher=dispatcher, clock=clock, tick_interval_seconds=0.1
    )

    runtime.start()
    snapshots = []

    def reader():
        for _ in range(10):
            snapshots.append(runtime.get_telemetry_snapshot())

    threads = [threading.Thread(target=reader) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    runtime.stop()
    assert len(snapshots) == 50


def test_19_health_monitor_consumes_telemetry():
    """Test 19: AutonomyModule get_telemetry() and get_diagnostics() serve observers cleanly."""
    cfg = ConfigurationManager()
    clock = TestClock("2026-08-17T10:00:00+00:00")
    mod = AutonomyModule(config=cfg, clock=clock)
    mod.on_initialize()

    diag = mod.get_diagnostics()
    assert diag["is_running"] is False

    telem = mod.get_telemetry()
    assert isinstance(telem, RuntimeTelemetrySnapshot)
    assert not telem.is_running


def test_20_shutdown_no_orphan_threads():
    """Test 20: Clean shutdown stops worker thread without leaving orphans."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    store.list_eligible_schedules.return_value = []
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(
        dispatcher=dispatcher, clock=clock, tick_interval_seconds=0.1
    )

    runtime.start()
    thread_ref = runtime._thread
    assert thread_ref is not None and thread_ref.is_alive()

    runtime.stop()
    assert not runtime.is_running
    assert not thread_ref.is_alive()


def test_21_stage6_compatibility():
    """Test 21: Full compatibility with Stage 6 self-recovery events and health checks."""
    bus = EventBus()
    events = []
    bus.subscribe("RuntimeWorkerLost", events.append)

    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    store.list_eligible_schedules.return_value = []
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock, event_bus=bus)

    runtime.start()
    runtime._running = True
    runtime._thread = None
    runtime.recover(reason="thread_lost")
    runtime.stop()

    assert len(events) == 1
    assert events[0].reason == "thread_lost"


def test_22_read_only_diagnostics_no_side_effects():
    """Test 22: RuntimeDiagnostics helper methods execute without side effects."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    diag = runtime.get_diagnostics()
    assert isinstance(diag, RuntimeDiagnostics)

    s1 = diag.get_snapshot()
    t1 = diag.get_telemetry()
    h1 = diag.get_history()

    assert not s1.is_running
    assert not t1.is_running
    assert isinstance(h1, list)
    assert not runtime.is_running  # Diagnostics query did NOT start runtime
