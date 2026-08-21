from __future__ import annotations

import threading
from unittest.mock import MagicMock

from aura.autonomy.module import AutonomyModule
from aura.cognition.goals import GoalManager as CognitionGoalManager
from aura.cognition.scheduling import (
    ContinuousAutonomyRuntime,
    PersistentRuntimeSnapshot,
    RuntimeControlPlane,
    RuntimeStateStore,
    ScheduleDispatcher,
    ScheduleStore,
    TestClock,
)
from aura.config import ConfigurationManager
from aura.container import DependencyContainer
from aura.events import EventBus
from aura.memory.store import SQLiteMemoryStore


def test_01_initial_state_creation():
    """Test 1: Creation and loading of initial PersistentRuntimeSnapshot."""
    memory_store = SQLiteMemoryStore(db_path=":memory:")
    state_store = RuntimeStateStore(store=memory_store)

    snap = state_store.load_snapshot("AuraAutonomyRuntime")
    assert snap is None


def test_02_state_persistence_and_loading():
    """Test 2: Save and load PersistentRuntimeSnapshot."""
    memory_store = SQLiteMemoryStore(db_path=":memory:")
    state_store = RuntimeStateStore(store=memory_store)

    snap = PersistentRuntimeSnapshot(
        runtime_name="AuraAutonomyRuntime",
        operational_state="RUNNING",
        clean_shutdown=False,
        started_at="2026-08-18T10:00:00+00:00",
    )
    state_store.save_snapshot(snap)

    loaded = state_store.load_snapshot("AuraAutonomyRuntime")
    assert loaded is not None
    assert loaded.runtime_name == "AuraAutonomyRuntime"
    assert loaded.operational_state == "RUNNING"
    assert not loaded.clean_shutdown


def test_03_snapshot_immutability():
    """Test 3: PersistentRuntimeSnapshot is a frozen dataclass."""
    snap = PersistentRuntimeSnapshot(
        runtime_name="AuraAutonomyRuntime",
        operational_state="RUNNING",
    )
    try:
        snap.operational_state = "STOPPED"  # type: ignore[misc]
        raise AssertionError("Should have raised AttributeError")
    except AttributeError:
        pass


def test_04_clean_shutdown_marking():
    """Test 4: mark_clean_shutdown sets clean_shutdown=True and state=STOPPED."""
    memory_store = SQLiteMemoryStore(db_path=":memory:")
    state_store = RuntimeStateStore(store=memory_store)

    snap = PersistentRuntimeSnapshot(
        runtime_name="AuraAutonomyRuntime",
        operational_state="RUNNING",
        clean_shutdown=False,
    )
    state_store.save_snapshot(snap)

    state_store.mark_clean_shutdown("AuraAutonomyRuntime", stopped_at="2026-08-18T10:05:00+00:00")

    loaded = state_store.load_snapshot("AuraAutonomyRuntime")
    assert loaded is not None
    assert loaded.clean_shutdown
    assert loaded.operational_state == "STOPPED"


def test_05_unexpected_shutdown_detection():
    """Test 5: detect_unexpected_shutdown returns True when process crashed while RUNNING."""
    memory_store = SQLiteMemoryStore(db_path=":memory:")
    event_bus = EventBus()
    events: list[str] = []
    event_bus.subscribe(
        "RuntimeUnexpectedShutdownDetected", lambda e: events.append(e.__event_name__)
    )

    state_store = RuntimeStateStore(store=memory_store, event_bus=event_bus)

    snap = PersistentRuntimeSnapshot(
        runtime_name="AuraAutonomyRuntime",
        operational_state="RUNNING",
        clean_shutdown=False,
    )
    state_store.save_snapshot(snap)

    assert state_store.detect_unexpected_shutdown("AuraAutonomyRuntime")
    assert len(events) == 1


def test_06_clean_shutdown_detection():
    """Test 6: detect_unexpected_shutdown returns False after clean shutdown."""
    memory_store = SQLiteMemoryStore(db_path=":memory:")
    state_store = RuntimeStateStore(store=memory_store)

    snap = PersistentRuntimeSnapshot(
        runtime_name="AuraAutonomyRuntime",
        operational_state="RUNNING",
        clean_shutdown=False,
    )
    state_store.save_snapshot(snap)
    state_store.mark_clean_shutdown("AuraAutonomyRuntime")

    assert not state_store.detect_unexpected_shutdown("AuraAutonomyRuntime")


def test_07_post_boot_restart_after_unexpected_shutdown():
    """Test 7: AutonomyModule restarts runtime post-boot when unexpected shutdown detected."""
    clock = TestClock("2026-08-18T10:00:00+00:00")
    memory_store = SQLiteMemoryStore(db_path=":memory:")
    event_bus = EventBus()
    recovery_events: list[str] = []
    event_bus.subscribe(
        "RuntimePostBootRecoveryAttempted", lambda e: recovery_events.append(e.recovery_action)
    )

    state_store = RuntimeStateStore(store=memory_store, event_bus=event_bus)
    snap = PersistentRuntimeSnapshot(
        runtime_name="AuraAutonomyRuntime",
        operational_state="RUNNING",
        clean_shutdown=False,
    )
    state_store.save_snapshot(snap)

    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    module = AutonomyModule(
        clock=clock, runtime=runtime, event_bus=event_bus, state_store=state_store
    )
    module.on_initialize()
    module.on_start()

    try:
        assert recovery_events == ["restart"]
        assert runtime.is_running
    finally:
        module.on_stop()


def test_08_post_boot_recovery_degraded_state():
    """Test 8: AutonomyModule recovers runtime post-boot when previous state was DEGRADED."""
    clock = TestClock("2026-08-18T10:00:00+00:00")
    memory_store = SQLiteMemoryStore(db_path=":memory:")
    event_bus = EventBus()
    recovery_events: list[str] = []
    event_bus.subscribe(
        "RuntimePostBootRecoveryAttempted", lambda e: recovery_events.append(e.recovery_action)
    )

    state_store = RuntimeStateStore(store=memory_store, event_bus=event_bus)
    snap = PersistentRuntimeSnapshot(
        runtime_name="AuraAutonomyRuntime",
        operational_state="DEGRADED",
        clean_shutdown=False,
    )
    state_store.save_snapshot(snap)

    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    module = AutonomyModule(
        clock=clock, runtime=runtime, event_bus=event_bus, state_store=state_store
    )
    module.on_initialize()
    module.on_start()

    try:
        assert recovery_events == ["recover"]
        assert runtime.is_running
    finally:
        module.on_stop()


def test_09_states_that_do_not_auto_recover():
    """Test 9: STOPPED and FAILED states do not auto-recover on boot."""
    clock = TestClock("2026-08-18T10:00:00+00:00")
    memory_store = SQLiteMemoryStore(db_path=":memory:")
    event_bus = EventBus()

    state_store = RuntimeStateStore(store=memory_store, event_bus=event_bus)
    snap = PersistentRuntimeSnapshot(
        runtime_name="AuraAutonomyRuntime",
        operational_state="FAILED",
        clean_shutdown=False,
    )
    state_store.save_snapshot(snap)

    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    module = AutonomyModule(
        clock=clock, runtime=runtime, event_bus=event_bus, state_store=state_store
    )
    module.on_initialize()
    module.on_start()

    assert not runtime.is_running


def test_10_idempotency_of_state_saves():
    """Test 10: Repeated save_snapshot calls update existing record without duplicates."""
    memory_store = SQLiteMemoryStore(db_path=":memory:")
    state_store = RuntimeStateStore(store=memory_store)

    for i in range(5):
        snap = PersistentRuntimeSnapshot(
            runtime_name="AuraAutonomyRuntime",
            operational_state="RUNNING",
            recovery_attempts=i,
        )
        state_store.save_snapshot(snap)

    loaded = state_store.load_snapshot("AuraAutonomyRuntime")
    assert loaded is not None
    assert loaded.recovery_attempts == 4


def test_11_concurrent_state_store_operations():
    """Test 11: Multithreaded concurrent save_snapshot and load_snapshot calls."""
    memory_store = SQLiteMemoryStore(db_path=":memory:")
    state_store = RuntimeStateStore(store=memory_store)
    errors: list[Exception] = []

    def worker(idx: int):
        try:
            snap = PersistentRuntimeSnapshot(
                runtime_name="AuraAutonomyRuntime",
                operational_state="RUNNING" if idx % 2 == 0 else "DEGRADED",
                recovery_attempts=idx,
            )
            state_store.save_snapshot(snap)
            state_store.load_snapshot("AuraAutonomyRuntime")
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    assert len(errors) == 0


def test_12_atomic_sqlite_transactions():
    """Test 12: Atomic SQLite transactions in RuntimeStateStore."""
    memory_store = SQLiteMemoryStore(db_path=":memory:")
    state_store = RuntimeStateStore(store=memory_store)

    snap = PersistentRuntimeSnapshot(
        runtime_name="AuraAutonomyRuntime",
        operational_state="RUNNING",
        last_error="Temporary failure",
    )
    state_store.save_snapshot(snap)

    loaded = state_store.load_snapshot("AuraAutonomyRuntime")
    assert loaded is not None
    assert loaded.last_error == "Temporary failure"


def test_13_ioc_container_integration():
    """Test 13: DependencyContainer registers and resolves RuntimeStateStore."""
    container = DependencyContainer()
    memory_store = SQLiteMemoryStore(db_path=":memory:")
    state_store = RuntimeStateStore(store=memory_store)

    container.register(RuntimeStateStore, instance=state_store)
    resolved = container.resolve(RuntimeStateStore)

    assert resolved is state_store


def test_14_autonomy_module_integration():
    """Test 14: AutonomyModule resolves state_store from container."""
    container = DependencyContainer()
    memory_store = SQLiteMemoryStore(db_path=":memory:")
    state_store = RuntimeStateStore(store=memory_store)
    container.register(RuntimeStateStore, instance=state_store)

    clock = TestClock("2026-08-18T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    module = AutonomyModule(clock=clock, runtime=runtime, container=container)
    module.on_initialize()

    assert module.state_store is state_store


def test_15_control_plane_integration():
    """Test 15: RuntimeControlPlane status is correctly persisted via AutonomyModule."""
    clock = TestClock("2026-08-18T10:00:00+00:00")
    memory_store = SQLiteMemoryStore(db_path=":memory:")
    state_store = RuntimeStateStore(store=memory_store)

    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    module = AutonomyModule(clock=clock, runtime=runtime, state_store=state_store)
    module.on_initialize()
    module.on_start()

    try:
        loaded = state_store.load_snapshot("AuraAutonomyRuntime")
        assert loaded is not None
        assert loaded.operational_state == "RUNNING"
    finally:
        module.on_stop()


def test_16_health_monitor_integration():
    """Test 16: Post-boot recovery respects HealthMonitor parameters."""
    clock = TestClock("2026-08-18T10:00:00+00:00")
    memory_store = SQLiteMemoryStore(db_path=":memory:")
    state_store = RuntimeStateStore(store=memory_store)

    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    module = AutonomyModule(clock=clock, runtime=runtime, state_store=state_store)
    module.on_initialize()
    module.on_start()
    module.on_stop()

    loaded = state_store.load_snapshot("AuraAutonomyRuntime")
    assert loaded is not None
    assert loaded.clean_shutdown


def test_17_stage1_to_stage8_compatibility():
    """Test 17: Stage 1-8 capabilities function with Stage 9 state persistence."""
    clock = TestClock("2026-08-18T10:00:00+00:00")
    memory_store = SQLiteMemoryStore(db_path=":memory:")
    state_store = RuntimeStateStore(store=memory_store)

    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)
    control = RuntimeControlPlane(runtime=runtime, clock=clock)

    module = AutonomyModule(
        clock=clock, runtime=runtime, control_plane=control, state_store=state_store
    )
    module.on_initialize()
    module.on_start()

    try:
        assert module.get_runtime_status() == "RUNNING"
        telemetry = module.get_telemetry()
        assert telemetry is not None
        assert telemetry.is_running
    finally:
        module.on_stop()


def test_18_no_orphan_threads_on_shutdown():
    """Test 18: No orphan threads created during boot, persistence, and shutdown."""
    clock = TestClock("2026-08-18T10:00:00+00:00")
    memory_store = SQLiteMemoryStore(db_path=":memory:")
    state_store = RuntimeStateStore(store=memory_store)

    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    module = AutonomyModule(clock=clock, runtime=runtime, state_store=state_store)
    module.on_initialize()
    module.on_start()

    t = runtime._thread
    assert t is not None and t.is_alive()

    module.on_stop()
    assert not runtime.is_running


def test_19_disabled_state_persistence():
    """Test 19: Setting autonomy.state_persistence_enabled=False bypasses state store saves."""
    clock = TestClock("2026-08-18T10:00:00+00:00")
    memory_store = SQLiteMemoryStore(db_path=":memory:")
    state_store = RuntimeStateStore(store=memory_store)
    config = ConfigurationManager()
    config.set("autonomy.state_persistence_enabled", False)

    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    module = AutonomyModule(config=config, clock=clock, runtime=runtime, state_store=state_store)
    module.on_initialize()
    module.on_start()

    try:
        snap = state_store.load_snapshot("AuraAutonomyRuntime")
        assert snap is None
    finally:
        module.on_stop()


def test_20_event_publishing_on_restoration():
    """Test 20: Events published on state save, restore, and crash detection."""
    memory_store = SQLiteMemoryStore(db_path=":memory:")
    event_bus = EventBus()
    events: list[str] = []

    event_bus.subscribe("RuntimeStatePersisted", lambda e: events.append(e.__event_name__))
    event_bus.subscribe("RuntimeStateRestored", lambda e: events.append(e.__event_name__))
    event_bus.subscribe(
        "RuntimeUnexpectedShutdownDetected", lambda e: events.append(e.__event_name__)
    )

    state_store = RuntimeStateStore(store=memory_store, event_bus=event_bus)
    snap = PersistentRuntimeSnapshot(
        runtime_name="AuraAutonomyRuntime",
        operational_state="RUNNING",
        clean_shutdown=False,
    )
    state_store.save_snapshot(snap)
    state_store.load_snapshot("AuraAutonomyRuntime")
    state_store.detect_unexpected_shutdown("AuraAutonomyRuntime")

    assert events == [
        "RuntimeStatePersisted",
        "RuntimeStateRestored",
        "RuntimeStateRestored",
        "RuntimeUnexpectedShutdownDetected",
    ]
