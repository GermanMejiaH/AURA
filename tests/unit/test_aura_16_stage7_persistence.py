from __future__ import annotations

import threading
from unittest.mock import MagicMock

from aura.autonomy.module import AutonomyModule
from aura.cognition.goals import GoalManager as CognitionGoalManager
from aura.cognition.scheduling import (
    ContinuousAutonomyRuntime,
    RuntimeHistoryStore,
    RuntimePersistenceHandler,
    RuntimeStateRecord,
    ScheduleDispatcher,
    ScheduleStore,
    TestClock,
)
from aura.config import ConfigurationManager
from aura.core.aura import AURA, AURABootOptions
from aura.events import (
    EventBus,
    RuntimeRecovered,
    RuntimeRecoveryAttempted,
    RuntimeRecoveryFailed,
    RuntimeStarted,
    RuntimeStopped,
    RuntimeTickCompleted,
    RuntimeTickFailed,
)
from aura.memory.store import SQLiteMemoryStore


def test_01_persistence_runtime_started(tmp_path):
    """Test 1: RuntimeStarted event updates state record and records event."""
    db_file = str(tmp_path / "aura.db")
    memory_store = SQLiteMemoryStore(db_path=db_file)
    store = RuntimeHistoryStore(store=memory_store)
    bus = EventBus()
    RuntimePersistenceHandler(store=store, event_bus=bus)

    bus.publish(
        RuntimeStarted(
            runtime_name="TestRuntime",
            tick_interval=1.0,
            started_at="2026-08-17T10:00:00+00:00",
        )
    )

    state = store.get_state("TestRuntime")
    assert state is not None
    assert state.status == "started"
    assert state.started_at == "2026-08-17T10:00:00+00:00"

    events = store.get_event_history("TestRuntime")
    assert len(events) == 1
    assert events[0].event_type == "RuntimeStarted"


def test_02_persistence_runtime_stopped(tmp_path):
    """Test 2: RuntimeStopped event updates state record and records event."""
    db_file = str(tmp_path / "aura.db")
    memory_store = SQLiteMemoryStore(db_path=db_file)
    store = RuntimeHistoryStore(store=memory_store)
    bus = EventBus()
    RuntimePersistenceHandler(store=store, event_bus=bus)

    bus.publish(
        RuntimeStopped(
            runtime_name="TestRuntime",
            tick_count=15,
            stopped_at="2026-08-17T10:30:00+00:00",
        )
    )

    state = store.get_state("TestRuntime")
    assert state is not None
    assert state.status == "stopped"
    assert state.stopped_at == "2026-08-17T10:30:00+00:00"
    assert state.tick_count == 15


def test_03_persistence_tick_completed(tmp_path):
    """Test 3: RuntimeTickCompleted increments tick counts and records event."""
    db_file = str(tmp_path / "aura.db")
    memory_store = SQLiteMemoryStore(db_path=db_file)
    store = RuntimeHistoryStore(store=memory_store)
    bus = EventBus()
    RuntimePersistenceHandler(store=store, event_bus=bus)

    bus.publish(
        RuntimeTickCompleted(
            tick_index=1,
            tick_timestamp="2026-08-17T10:01:00+00:00",
            dispatched_count=2,
        )
    )

    state = store.get_state("AuraAutonomyRuntime")
    assert state is not None
    assert state.tick_count == 1
    assert state.successful_ticks == 1
    assert state.last_successful_tick_at == "2026-08-17T10:01:00+00:00"


def test_04_persistence_tick_failed(tmp_path):
    """Test 4: RuntimeTickFailed updates failed_ticks, last_error, and records event."""
    db_file = str(tmp_path / "aura.db")
    memory_store = SQLiteMemoryStore(db_path=db_file)
    store = RuntimeHistoryStore(store=memory_store)
    bus = EventBus()
    RuntimePersistenceHandler(store=store, event_bus=bus)

    bus.publish(
        RuntimeTickFailed(
            tick_index=2,
            tick_timestamp="2026-08-17T10:02:00+00:00",
            error="Connection timeout",
        )
    )

    state = store.get_state("AuraAutonomyRuntime")
    assert state is not None
    assert state.failed_ticks == 1
    assert state.last_error == "Connection timeout"

    failed_events = store.get_failed_ticks("AuraAutonomyRuntime")
    assert len(failed_events) == 1


def test_05_persistence_recovery_attempted(tmp_path):
    """Test 5: RuntimeRecoveryAttempted increments recovery count and records event."""
    db_file = str(tmp_path / "aura.db")
    memory_store = SQLiteMemoryStore(db_path=db_file)
    store = RuntimeHistoryStore(store=memory_store)
    bus = EventBus()
    RuntimePersistenceHandler(store=store, event_bus=bus)

    bus.publish(
        RuntimeRecoveryAttempted(
            runtime_name="AuraAutonomyRuntime",
            attempt_number=1,
            reason="worker_thread_dead",
        )
    )

    state = store.get_state("AuraAutonomyRuntime")
    assert state is not None
    assert state.recovery_attempts_count == 1
    assert state.status == "recovering"


def test_06_persistence_recovered(tmp_path):
    """Test 6: RuntimeRecovered restores status to started and records event."""
    db_file = str(tmp_path / "aura.db")
    memory_store = SQLiteMemoryStore(db_path=db_file)
    store = RuntimeHistoryStore(store=memory_store)
    bus = EventBus()
    RuntimePersistenceHandler(store=store, event_bus=bus)

    bus.publish(
        RuntimeRecovered(
            runtime_name="AuraAutonomyRuntime",
            attempt_number=1,
            recovered_at="2026-08-17T10:05:00+00:00",
        )
    )

    state = store.get_state("AuraAutonomyRuntime")
    assert state is not None
    assert state.status == "started"
    assert state.last_recovery_at == "2026-08-17T10:05:00+00:00"


def test_07_persistence_recovery_failed(tmp_path):
    """Test 7: RuntimeRecoveryFailed sets status to degraded and increments failure count."""
    db_file = str(tmp_path / "aura.db")
    memory_store = SQLiteMemoryStore(db_path=db_file)
    store = RuntimeHistoryStore(store=memory_store)
    bus = EventBus()
    RuntimePersistenceHandler(store=store, event_bus=bus)

    bus.publish(
        RuntimeRecoveryFailed(
            runtime_name="AuraAutonomyRuntime",
            attempt_number=4,
            reason="max_attempts_exceeded",
        )
    )

    state = store.get_state("AuraAutonomyRuntime")
    assert state is not None
    assert state.status == "degraded"
    assert state.recovery_failures_count == 1


def test_08_query_last_state(tmp_path):
    """Test 8: get_state() retrieves latest persisted state accurately."""
    db_file = str(tmp_path / "aura.db")
    memory_store = SQLiteMemoryStore(db_path=db_file)
    store = RuntimeHistoryStore(store=memory_store)

    record = RuntimeStateRecord(
        runtime_name="CustomRuntime",
        status="started",
        started_at="2026-08-17T10:00:00+00:00",
        tick_count=42,
    )
    store.save_state(record)

    retrieved = store.get_state("CustomRuntime")
    assert retrieved is not None
    assert retrieved.runtime_name == "CustomRuntime"
    assert retrieved.tick_count == 42


def test_09_query_event_history(tmp_path):
    """Test 9: get_event_history() filters events by runtime_name and event_type."""
    db_file = str(tmp_path / "aura.db")
    memory_store = SQLiteMemoryStore(db_path=db_file)
    store = RuntimeHistoryStore(store=memory_store)

    store.record_event("RuntimeA", "RuntimeStarted", "2026-08-17T10:00:00+00:00", {})
    store.record_event("RuntimeB", "RuntimeStarted", "2026-08-17T10:01:00+00:00", {})
    store.record_event("RuntimeA", "RuntimeStopped", "2026-08-17T10:10:00+00:00", {})

    history_a = store.get_event_history("RuntimeA")
    assert len(history_a) == 2

    history_a_started = store.get_event_history("RuntimeA", event_type="RuntimeStarted")
    assert len(history_a_started) == 1
    assert history_a_started[0].event_type == "RuntimeStarted"


def test_10_no_history_empty_db(tmp_path):
    """Test 10: Querying empty database returns None for state and empty list for events."""
    db_file = str(tmp_path / "aura.db")
    memory_store = SQLiteMemoryStore(db_path=db_file)
    store = RuntimeHistoryStore(store=memory_store)

    assert store.get_state("NonExistent") is None
    assert store.get_event_history("NonExistent") == []
    assert store.detect_interrupted_run("NonExistent") is False


def test_11_persistence_disabled_configuration(tmp_path):
    """Test 11: Disabling autonomy.persistence_enabled=False bypasses history handler setup."""
    cfg = ConfigurationManager()
    cfg.load_from_dict({"autonomy.persistence_enabled": False})

    opts = AURABootOptions(enable_scheduler=False, enable_health_monitor=False)
    aura = AURA(options=opts, config=cfg)
    aura.boot()

    mod = aura.module_manager.get("autonomy") if aura.module_manager else None
    assert isinstance(mod, AutonomyModule)
    assert mod.history_store is None
    assert mod.persistence_handler is None

    aura.shutdown(wait=True)


def test_12_persistence_failure_does_not_crash_runtime(tmp_path):
    """Test 12: DB errors during event handling do not throw uncaught exceptions or stop ticks."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    store.list_eligible_schedules.return_value = []
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)

    # Broken history store that throws on save
    broken_history = MagicMock(spec=RuntimeHistoryStore)
    broken_history.save_state.side_effect = RuntimeError("SQLite DB Locked")
    broken_history.record_event.side_effect = RuntimeError("SQLite DB Locked")

    bus = EventBus()
    RuntimePersistenceHandler(store=broken_history, event_bus=bus)
    runtime = ContinuousAutonomyRuntime(
        dispatcher=dispatcher, clock=clock, event_bus=bus, tick_interval_seconds=0.1
    )

    # Should not raise exception
    results = runtime.tick()
    assert results == []
    assert runtime.tick_count == 1


def test_13_aura_restart_rehydration_no_auto_worker(tmp_path):
    """Test 13: Restarting AURA loads state without auto-spawning worker before on_start."""
    db_file = str(tmp_path / "aura.db")
    memory_store = SQLiteMemoryStore(db_path=db_file)
    store = RuntimeHistoryStore(store=memory_store)

    # Simulate last process left status = "started"
    store.save_state(RuntimeStateRecord(runtime_name="AuraAutonomyRuntime", status="started"))

    cfg = ConfigurationManager()
    cfg.load_from_dict(
        {
            "autonomy.persistence_enabled": True,
            "autonomy.runtime_enabled": False,  # Disabled to verify rehydration
        }
    )

    opts = AURABootOptions(enable_scheduler=False, enable_health_monitor=False)
    aura = AURA(options=opts, config=cfg)
    aura.container.register(RuntimeHistoryStore, instance=store)
    aura.boot()

    mod = aura.module_manager.get("autonomy") if aura.module_manager else None
    assert isinstance(mod, AutonomyModule)
    assert mod.runtime is not None
    # Worker must NOT be running because runtime_enabled is False
    assert not mod.runtime.is_running

    aura.shutdown(wait=True)


def test_14_crash_detection(tmp_path):
    """Test 14: detect_interrupted_run() returns True when last state was started without stop."""
    db_file = str(tmp_path / "aura.db")
    memory_store = SQLiteMemoryStore(db_path=db_file)
    store = RuntimeHistoryStore(store=memory_store)

    store.save_state(RuntimeStateRecord(runtime_name="TestRuntime", status="started"))
    store.record_event("TestRuntime", "RuntimeStarted", "2026-08-17T10:00:00+00:00", {})

    assert store.detect_interrupted_run("TestRuntime") is True

    # Record clean stop
    store.record_event("TestRuntime", "RuntimeStopped", "2026-08-17T10:30:00+00:00", {})
    store.save_state(RuntimeStateRecord(runtime_name="TestRuntime", status="stopped"))

    assert store.detect_interrupted_run("TestRuntime") is False


def test_15_thread_safety_queries(tmp_path):
    """Test 15: Concurrent reads/writes to RuntimeHistoryStore execute safely."""
    db_file = str(tmp_path / "aura.db")
    memory_store = SQLiteMemoryStore(db_path=db_file)
    store = RuntimeHistoryStore(store=memory_store)

    def writer(idx: int):
        for i in range(10):
            store.save_state(
                RuntimeStateRecord(
                    runtime_name="AuraAutonomyRuntime",
                    status="started",
                    tick_count=idx * 10 + i,
                )
            )
            store.record_event(
                "AuraAutonomyRuntime",
                "RuntimeTickCompleted",
                f"2026-08-17T10:{idx:02d}:{i:02d}+00:00",
                {"tick_index": idx * 10 + i},
            )

    threads = [threading.Thread(target=writer, args=(t,)) for t in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    state = store.get_state("AuraAutonomyRuntime")
    assert state is not None
    history = store.get_event_history("AuraAutonomyRuntime", limit=100)
    assert len(history) == 50


def test_16_no_duplicate_events(tmp_path):
    """Test 16: Events are recorded exactly once per published EventBus event."""
    db_file = str(tmp_path / "aura.db")
    memory_store = SQLiteMemoryStore(db_path=db_file)
    store = RuntimeHistoryStore(store=memory_store)
    bus = EventBus()
    RuntimePersistenceHandler(store=store, event_bus=bus)

    bus.publish(
        RuntimeStarted(
            runtime_name="AuraAutonomyRuntime",
            tick_interval=1.0,
            started_at="2026-08-17T10:00:00+00:00",
        )
    )

    history = store.get_event_history("AuraAutonomyRuntime")
    assert len(history) == 1


def test_17_history_event_pruning(tmp_path):
    """Test 17: Event count exceeding max_events prunes old entries cleanly."""
    db_file = str(tmp_path / "aura.db")
    memory_store = SQLiteMemoryStore(db_path=db_file)
    store = RuntimeHistoryStore(store=memory_store, max_events=5)

    for i in range(10):
        store.record_event(
            "AuraAutonomyRuntime",
            "RuntimeTickCompleted",
            f"2026-08-17T10:00:{i:02d}+00:00",
            {"tick": i},
        )

    history = store.get_event_history("AuraAutonomyRuntime", limit=20)
    assert len(history) == 5


def test_18_compatibility_with_test_clock(tmp_path):
    """Test 18: RuntimeHistoryStore works deterministically with TestClock timestamps."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    db_file = str(tmp_path / "aura.db")
    memory_store = SQLiteMemoryStore(db_path=db_file)
    store = RuntimeHistoryStore(store=memory_store)

    store.record_event("AuraAutonomyRuntime", "CustomEvent", clock.now_iso(), {})
    clock.advance(seconds=120)
    store.record_event("AuraAutonomyRuntime", "CustomEvent2", clock.now_iso(), {})

    history = store.get_event_history("AuraAutonomyRuntime")
    assert len(history) == 2
    assert history[0].event_timestamp == "2026-08-17T10:02:00+00:00"
    assert history[1].event_timestamp == "2026-08-17T10:00:00+00:00"


def test_19_ioc_container_integration(tmp_path):
    """Test 19: RuntimeHistoryStore is registered in DependencyContainer on boot."""
    cfg = ConfigurationManager()
    cfg.load_from_dict({"autonomy.persistence_enabled": True})

    opts = AURABootOptions(enable_scheduler=False, enable_health_monitor=False)
    aura = AURA(options=opts, config=cfg)
    aura.boot()

    assert aura.container.has(RuntimeHistoryStore)
    resolved_store = aura.container.resolve(RuntimeHistoryStore)
    assert isinstance(resolved_store, RuntimeHistoryStore)

    aura.shutdown(wait=True)


def test_20_aggregate_stats_computation(tmp_path):
    """Test 20: get_aggregate_stats() computes boots, shutdowns, ticks, and recoveries."""
    db_file = str(tmp_path / "aura.db")
    memory_store = SQLiteMemoryStore(db_path=db_file)
    store = RuntimeHistoryStore(store=memory_store)

    store.record_event(
        "AuraAutonomyRuntime",
        "RuntimeStarted",
        "2026-08-17T10:00:00+00:00",
        {},
    )
    store.record_event(
        "AuraAutonomyRuntime",
        "RuntimeStopped",
        "2026-08-17T10:30:00+00:00",
        {},
    )
    store.record_event(
        "AuraAutonomyRuntime",
        "RuntimeRecoveryAttempted",
        "2026-08-17T10:15:00+00:00",
        {},
    )
    store.save_state(
        RuntimeStateRecord(
            runtime_name="AuraAutonomyRuntime",
            status="stopped",
            tick_count=100,
            successful_ticks=95,
            failed_ticks=5,
        )
    )

    stats = store.get_aggregate_stats("AuraAutonomyRuntime")
    assert stats.runtime_name == "AuraAutonomyRuntime"
    assert stats.total_boots == 1
    assert stats.total_shutdowns == 1
    assert stats.total_ticks == 100
    assert stats.total_successful_ticks == 95
    assert stats.total_failed_ticks == 5
    assert stats.total_recovery_attempts == 1
