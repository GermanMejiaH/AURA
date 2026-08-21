from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from aura.autonomy.agent_models import AgentGoal, AgentPlan, AgentTask, TaskStatus
from aura.autonomy.executor import AgentExecutionResult, AgentExecutor
from aura.autonomy.planner import AgentPlanner
from aura.cognition.goals import GoalManager, GoalPriority, GoalStatus, GoalStore
from aura.cognition.scheduling import (
    ContinuousAutonomyRuntime,
    ScheduleDispatcher,
    ScheduleStatus,
    ScheduleStore,
    ScheduleType,
    SystemClock,
    TemporalSchedule,
    TestClock,
)
from aura.events.bus import EventBus
from aura.events.models import (
    RuntimeStarted,
    RuntimeStopped,
    RuntimeTickCompleted,
    RuntimeTickFailed,
)
from aura.memory.store import SQLiteMemoryStore


def test_01_runtime_starts_and_stops_cleanly(tmp_path):
    """Test 01: ContinuousAutonomyRuntime starts and stops cleanly."""
    db_file = str(tmp_path / "runtime_stage4_1.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    sched_store = ScheduleStore(store=sql_store)
    dispatcher = ScheduleDispatcher(schedule_store=sched_store, goal_manager=goal_mgr)

    runtime = ContinuousAutonomyRuntime(
        dispatcher=dispatcher,
        tick_interval_seconds=0.05,
    )

    assert not runtime.is_running
    runtime.start()
    assert runtime.is_running

    runtime.stop(timeout=1.0)
    assert not runtime.is_running


def test_02_start_is_idempotent(tmp_path):
    """Test 02: Calling start() multiple times is idempotent."""
    db_file = str(tmp_path / "runtime_stage4_2.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    sched_store = ScheduleStore(store=sql_store)
    dispatcher = ScheduleDispatcher(schedule_store=sched_store, goal_manager=goal_mgr)

    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, tick_interval_seconds=0.05)
    runtime.start()
    assert runtime.is_running

    # Second start call is a no-op
    runtime.start()
    assert runtime.is_running

    runtime.stop(timeout=1.0)


def test_03_stop_is_idempotent(tmp_path):
    """Test 03: Calling stop() multiple times is idempotent."""
    db_file = str(tmp_path / "runtime_stage4_3.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    sched_store = ScheduleStore(store=sql_store)
    dispatcher = ScheduleDispatcher(schedule_store=sched_store, goal_manager=goal_mgr)

    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, tick_interval_seconds=0.05)
    runtime.start()
    runtime.stop(timeout=1.0)
    assert not runtime.is_running

    # Second stop call is a no-op
    runtime.stop(timeout=1.0)
    assert not runtime.is_running


def test_04_manual_tick_invokes_dispatcher(tmp_path):
    """Test 04: Manual tick() call executes due schedules via ScheduleDispatcher."""
    db_file = str(tmp_path / "runtime_stage4_4.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    sched_store = ScheduleStore(store=sql_store)

    goal = goal_mgr.create_goal("Manual tick goal")
    past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    sched = TemporalSchedule(
        goal_id=goal.goal_id, schedule_type=ScheduleType.ONE_SHOT, next_run_at=past
    )
    sched_store.save_schedule(sched)

    dispatcher = ScheduleDispatcher(schedule_store=sched_store, goal_manager=goal_mgr)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher)

    results = runtime.tick()
    assert len(results) == 1
    assert results[0].dispatched is True
    assert runtime.tick_count == 1
    assert runtime.last_tick_at is not None


def test_05_tick_uses_injected_test_clock(tmp_path):
    """Test 05: TestClock fast-forwards time instantly without real-world sleep."""
    db_file = str(tmp_path / "runtime_stage4_5.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    sched_store = ScheduleStore(store=sql_store)

    start_iso = "2026-08-16T12:00:00+00:00"
    clock = TestClock(initial_time=start_iso)

    goal = goal_mgr.create_goal("TestClock goal")
    target_iso = "2026-08-16T12:05:00+00:00"
    sched = TemporalSchedule(
        goal_id=goal.goal_id,
        schedule_type=ScheduleType.ONE_SHOT,
        next_run_at=target_iso,
    )
    sched_store.save_schedule(sched)

    dispatcher = ScheduleDispatcher(schedule_store=sched_store, goal_manager=goal_mgr)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    # 1. Tick at 12:00:00 -> not due
    res1 = runtime.tick()
    assert len(res1) == 0

    # 2. Fast-forward clock by 10 minutes (to 12:10:00)
    clock.advance(600)
    res2 = runtime.tick()
    assert len(res2) == 1
    assert res2[0].dispatched is True
    assert res2[0].status == ScheduleStatus.COMPLETED


def test_06_due_schedule_dispatched_in_tick(tmp_path):
    """Test 06: Due schedule is dispatched in tick and persisted in SQLite."""
    db_file = str(tmp_path / "runtime_stage4_6.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    sched_store = ScheduleStore(store=sql_store)

    goal = goal_mgr.create_goal("Due schedule goal")
    past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    sched = TemporalSchedule(
        goal_id=goal.goal_id, schedule_type=ScheduleType.ONE_SHOT, next_run_at=past
    )
    sched_store.save_schedule(sched)

    dispatcher = ScheduleDispatcher(schedule_store=sched_store, goal_manager=goal_mgr)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher)

    results = runtime.tick()
    assert len(results) == 1
    assert results[0].dispatched is True

    retrieved = sched_store.get_schedule(sched.schedule_id)
    assert retrieved is not None
    assert retrieved.status == ScheduleStatus.COMPLETED


def test_07_non_due_schedule_ignored_in_tick(tmp_path):
    """Test 07: Future schedule is ignored during tick."""
    db_file = str(tmp_path / "runtime_stage4_7.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    sched_store = ScheduleStore(store=sql_store)

    goal = goal_mgr.create_goal("Future goal")
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    sched = TemporalSchedule(
        goal_id=goal.goal_id, schedule_type=ScheduleType.ONE_SHOT, next_run_at=future
    )
    sched_store.save_schedule(sched)

    dispatcher = ScheduleDispatcher(schedule_store=sched_store, goal_manager=goal_mgr)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher)

    results = runtime.tick()
    assert len(results) == 0


def test_08_overlapping_tick_skipped_gracefully(tmp_path):
    """Test 08: Locked _tick_lock causes overlapping tick to be skipped gracefully."""
    db_file = str(tmp_path / "runtime_stage4_8.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    sched_store = ScheduleStore(store=sql_store)
    dispatcher = ScheduleDispatcher(schedule_store=sched_store, goal_manager=goal_mgr)

    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher)

    # Manually acquire _tick_lock to simulate ongoing long tick
    runtime._tick_lock.acquire()

    try:
        results = runtime.tick()
        assert results == []
    finally:
        runtime._tick_lock.release()


def test_09_dispatcher_exception_handled_in_runtime(tmp_path):
    """Test 09: Exception in dispatcher is caught, logs error, and publishes RuntimeTickFailed."""
    event_bus = EventBus()

    mock_dispatcher = MagicMock(spec=ScheduleDispatcher)
    mock_dispatcher.process_due_schedules.side_effect = RuntimeError("Database connection lost")

    failed_events: list[RuntimeTickFailed] = []
    event_bus.subscribe(RuntimeTickFailed, lambda e: failed_events.append(e))  # type: ignore[arg-type]

    runtime = ContinuousAutonomyRuntime(
        dispatcher=mock_dispatcher,
        event_bus=event_bus,
    )

    results = runtime.tick()
    assert results == []
    assert len(failed_events) == 1
    assert "Database connection lost" in failed_events[0].error


def test_10_individual_goal_failure_does_not_stop_runtime(tmp_path):
    """Test 10: Individual goal failure in execution does not crash runtime."""
    db_file = str(tmp_path / "runtime_stage4_10.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    sched_store = ScheduleStore(store=sql_store)

    goal = goal_mgr.create_goal("Failing goal")
    past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    sched = TemporalSchedule(
        goal_id=goal.goal_id, schedule_type=ScheduleType.ONE_SHOT, next_run_at=past
    )
    sched_store.save_schedule(sched)

    mock_planner = MagicMock(spec=AgentPlanner)
    mock_planner.deliberate_and_plan.side_effect = RuntimeError("Planner failure")

    dispatcher = ScheduleDispatcher(
        schedule_store=sched_store,
        goal_manager=goal_mgr,
        planner=mock_planner,
    )
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher)

    results = runtime.tick()
    assert len(results) == 1
    assert results[0].dispatched is False
    assert "Planner failure" in results[0].reason

    # Goal is marked FAILED, runtime remains operational
    updated_goal = goal_mgr.get_goal(goal.goal_id)
    assert updated_goal is not None
    assert updated_goal.status == GoalStatus.FAILED


def test_11_clean_shutdown_wakes_immediately_from_sleep(tmp_path):
    """Test 11: stop() wakes worker thread immediately without waiting for full interval."""
    db_file = str(tmp_path / "runtime_stage4_11.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    sched_store = ScheduleStore(store=sql_store)
    dispatcher = ScheduleDispatcher(schedule_store=sched_store, goal_manager=goal_mgr)

    # Set long tick interval (60 seconds)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, tick_interval_seconds=60.0)

    start_t = datetime.now(UTC)
    runtime.start()

    # Immediately stop
    runtime.stop(timeout=2.0)
    stop_t = datetime.now(UTC)

    # Stop completed in far less than 60 seconds (woke immediately from wait)
    assert (stop_t - start_t).total_seconds() < 5.0
    assert not runtime.is_running


def test_12_shutdown_timeout_handled(tmp_path):
    """Test 12: Handles thread join timeout gracefully when worker thread is busy."""
    db_file = str(tmp_path / "runtime_stage4_12.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    sched_store = ScheduleStore(store=sql_store)
    dispatcher = ScheduleDispatcher(schedule_store=sched_store, goal_manager=goal_mgr)

    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher)
    runtime.start()

    # Stop with very short timeout
    runtime.stop(timeout=0.01)
    assert not runtime.is_running


def test_13_events_emitted_during_runtime_lifecycle(tmp_path):
    """Test 13: RuntimeStarted, RuntimeStopped, and RuntimeTickCompleted events published."""
    db_file = str(tmp_path / "runtime_stage4_13.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    sched_store = ScheduleStore(store=sql_store)
    dispatcher = ScheduleDispatcher(schedule_store=sched_store, goal_manager=goal_mgr)
    event_bus = EventBus()

    started_events: list[RuntimeStarted] = []
    stopped_events: list[RuntimeStopped] = []
    completed_events: list[RuntimeTickCompleted] = []

    event_bus.subscribe(RuntimeStarted, lambda e: started_events.append(e))  # type: ignore[arg-type]
    event_bus.subscribe(RuntimeStopped, lambda e: stopped_events.append(e))  # type: ignore[arg-type]
    event_bus.subscribe(RuntimeTickCompleted, lambda e: completed_events.append(e))  # type: ignore[arg-type]

    runtime = ContinuousAutonomyRuntime(
        dispatcher=dispatcher,
        event_bus=event_bus,
        tick_interval_seconds=0.05,
    )

    runtime.start()
    runtime.tick()
    runtime.stop(timeout=1.0)

    assert len(started_events) == 1
    assert len(stopped_events) == 1
    assert len(completed_events) == 1
    assert started_events[0].runtime_name == "AuraAutonomyRuntime"


def test_14_fast_forward_test_clock_drives_multiple_intervals(tmp_path):
    """Test 14: Fast-forwarding TestClock drives multi-step INTERVAL schedule."""
    db_file = str(tmp_path / "runtime_stage4_14.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    sched_store = ScheduleStore(store=sql_store)

    clock = TestClock(initial_time="2026-08-16T10:00:00+00:00")
    goal = goal_mgr.create_goal("Multi-step interval goal")

    # Schedule every 300 seconds (5 min)
    sched = TemporalSchedule(
        goal_id=goal.goal_id,
        schedule_type=ScheduleType.INTERVAL,
        expression="300",
        next_run_at="2026-08-16T10:00:00+00:00",
    )
    sched_store.save_schedule(sched)

    dispatcher = ScheduleDispatcher(schedule_store=sched_store, goal_manager=goal_mgr)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    # Tick 1 at 10:00:00 -> dispatches run 1
    res1 = runtime.tick()
    assert len(res1) == 1
    assert res1[0].iterations_count == 1

    # Tick 2 at 10:01:00 -> not due
    clock.advance(60)
    res2 = runtime.tick()
    assert len(res2) == 0

    # Tick 3 at 10:05:00 -> dispatches run 2
    clock.advance(240)
    res3 = runtime.tick()
    assert len(res3) == 1
    assert res3[0].iterations_count == 2


def test_15_concurrent_start_stop_thread_safe(tmp_path):
    """Test 15: Concurrent start/stop calls from multiple threads are safe."""
    db_file = str(tmp_path / "runtime_stage4_15.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    sched_store = ScheduleStore(store=sql_store)
    dispatcher = ScheduleDispatcher(schedule_store=sched_store, goal_manager=goal_mgr)

    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, tick_interval_seconds=0.05)

    threads: list[threading.Thread] = []
    for _ in range(5):
        t1 = threading.Thread(target=runtime.start)
        t2 = threading.Thread(target=lambda: runtime.stop(timeout=1.0))
        threads.extend([t1, t2])

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Ensure clean final state
    runtime.stop(timeout=1.0)
    assert not runtime.is_running


def test_16_aura_15_compatibility_unaffected(tmp_path):
    """Test 16: Full E2E integration with GoalManager, AgentPlanner, and AgentExecutor."""
    db_file = str(tmp_path / "runtime_stage4_16.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    sched_store = ScheduleStore(store=sql_store)

    goal = goal_mgr.create_goal("E2E Runtime Goal", priority=GoalPriority.HIGH)
    past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    sched = TemporalSchedule(
        goal_id=goal.goal_id, schedule_type=ScheduleType.ONE_SHOT, next_run_at=past
    )
    sched_store.save_schedule(sched)

    planner = MagicMock(spec=AgentPlanner)
    executor = MagicMock(spec=AgentExecutor)
    mock_plan = AgentPlan(
        goal=AgentGoal(description="E2E Runtime Goal"),
        tasks=[AgentTask(description="Task 1", status=TaskStatus.SUCCESS)],
    )
    planner.deliberate_and_plan.return_value = (MagicMock(), mock_plan)
    executor.execute_plan.return_value = AgentExecutionResult(
        plan_id=mock_plan.plan_id, completed=True
    )

    dispatcher = ScheduleDispatcher(
        schedule_store=sched_store,
        goal_manager=goal_mgr,
        planner=planner,
        executor=executor,
    )
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher)

    results = runtime.tick()
    assert len(results) == 1
    assert results[0].dispatched is True

    updated_goal = goal_mgr.get_goal(goal.goal_id)
    assert updated_goal is not None
    assert updated_goal.status == GoalStatus.COMPLETED


def test_17_clock_set_time_and_advance():
    """Test 17: TestClock methods (set_time, advance, SystemClock) operate accurately."""
    sys_clock = SystemClock()
    assert sys_clock.now().tzinfo is not None
    assert sys_clock.now_iso() is not None

    test_clock = TestClock("2026-08-16T12:00:00+00:00")
    assert test_clock.now_iso() == "2026-08-16T12:00:00+00:00"

    test_clock.set_time("2026-08-16T15:30:00+00:00")
    assert test_clock.now_iso() == "2026-08-16T15:30:00+00:00"

    test_clock.advance(timedelta(minutes=30))
    assert test_clock.now_iso() == "2026-08-16T16:00:00+00:00"


def test_18_concurrent_start_calls_create_single_worker(tmp_path):
    """Test 18: Multiple concurrent start() calls create only one active worker thread."""
    db_file = str(tmp_path / "runtime_stage4_18.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    sched_store = ScheduleStore(store=sql_store)
    dispatcher = ScheduleDispatcher(schedule_store=sched_store, goal_manager=goal_mgr)

    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, tick_interval_seconds=0.05)

    threads = [threading.Thread(target=runtime.start) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert runtime.is_running
    assert runtime._thread is not None
    assert runtime._thread.is_alive()

    runtime.stop(timeout=1.0)
    assert not runtime.is_running


def test_19_concurrent_stop_calls_consistent_state(tmp_path):
    """Test 19: Multiple concurrent stop() calls leave runtime in consistent stopped state."""
    db_file = str(tmp_path / "runtime_stage4_19.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    sched_store = ScheduleStore(store=sql_store)
    dispatcher = ScheduleDispatcher(schedule_store=sched_store, goal_manager=goal_mgr)

    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, tick_interval_seconds=0.05)
    runtime.start()

    threads = [threading.Thread(target=lambda: runtime.stop(timeout=1.0)) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not runtime.is_running
    assert runtime._thread is None


def test_20_restart_cycle_start_stop_start_stop_works(tmp_path):
    """Test 20: Full restart cycle (start -> stop -> start -> stop) operates correctly."""
    db_file = str(tmp_path / "runtime_stage4_20.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    sched_store = ScheduleStore(store=sql_store)
    dispatcher = ScheduleDispatcher(schedule_store=sched_store, goal_manager=goal_mgr)

    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, tick_interval_seconds=0.05)

    # First cycle
    runtime.start()
    assert runtime.is_running
    runtime.stop(timeout=1.0)
    assert not runtime.is_running

    # Second cycle (Restart)
    runtime.start()
    assert runtime.is_running
    runtime.stop(timeout=1.0)
    assert not runtime.is_running


def test_21_concurrent_test_clock_advance_and_read():
    """Test 21: Concurrent advance() and now_iso() calls on TestClock are thread-safe."""
    clock = TestClock("2026-08-16T12:00:00+00:00")

    def advancer():
        for _ in range(100):
            clock.advance(1)

    def reader():
        for _ in range(100):
            _ = clock.now_iso()

    threads = [
        threading.Thread(target=advancer),
        threading.Thread(target=reader),
        threading.Thread(target=advancer),
        threading.Thread(target=reader),
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Total advance: 200 seconds -> 12:00:00 + 200s = 12:03:20
    assert clock.now_iso() == "2026-08-16T12:03:20+00:00"
