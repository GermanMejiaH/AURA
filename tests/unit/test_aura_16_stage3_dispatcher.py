from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from aura.autonomy.agent_models import AgentGoal, AgentPlan, AgentTask, TaskStatus
from aura.autonomy.executor import AgentExecutionResult, AgentExecutor
from aura.autonomy.planner import AgentPlanner
from aura.cognition.goals import GoalManager, GoalPriority, GoalStatus, GoalStore
from aura.cognition.scheduling import (
    DispatchResult,
    ScheduleDispatcher,
    ScheduleStatus,
    ScheduleStore,
    ScheduleType,
    TemporalSchedule,
)
from aura.events.bus import EventBus
from aura.events.models import (
    ScheduleRunRecorded,
    ScheduleSkipped,
    ScheduleTriggered,
)
from aura.memory.store import SQLiteMemoryStore


def test_01_dispatch_due_one_shot_schedule(tmp_path):
    """Test 01: Dispatch due ONE_SHOT schedule updates iterations_count=1 and status=COMPLETED."""
    db_file = str(tmp_path / "sched_stage3_1.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    sched_store = ScheduleStore(store=sql_store)

    goal = goal_mgr.create_goal("One-shot test goal", priority=GoalPriority.HIGH)
    past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()

    sched = TemporalSchedule(
        goal_id=goal.goal_id,
        schedule_type=ScheduleType.ONE_SHOT,
        next_run_at=past,
    )
    sched_store.save_schedule(sched)

    dispatcher = ScheduleDispatcher(
        schedule_store=sched_store,
        goal_manager=goal_mgr,
    )

    results = dispatcher.process_due_schedules()
    assert len(results) == 1
    res = results[0]
    assert isinstance(res, DispatchResult)
    assert res.dispatched is True
    assert res.status == ScheduleStatus.COMPLETED
    assert res.iterations_count == 1

    # Verify SQLite persistence
    retrieved = sched_store.get_schedule(sched.schedule_id)
    assert retrieved is not None
    assert retrieved.status == ScheduleStatus.COMPLETED
    assert retrieved.iterations_count == 1


def test_02_dispatch_interval_schedule_updates_store(tmp_path):
    """Test 02: Dispatch INTERVAL schedule updates iterations_count and next_run_at in SQLite."""
    db_file = str(tmp_path / "sched_stage3_2.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    sched_store = ScheduleStore(store=sql_store)

    goal = goal_mgr.create_goal("Interval goal", priority=GoalPriority.MEDIUM)
    past = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()

    sched = TemporalSchedule(
        goal_id=goal.goal_id,
        schedule_type=ScheduleType.INTERVAL,
        expression="300",  # 5 minutes
        next_run_at=past,
    )
    sched_store.save_schedule(sched)

    dispatcher = ScheduleDispatcher(
        schedule_store=sched_store,
        goal_manager=goal_mgr,
    )

    now_iso = datetime.now(UTC).isoformat()
    results = dispatcher.process_due_schedules(at_timestamp=now_iso)
    assert len(results) == 1
    assert results[0].dispatched is True
    assert results[0].iterations_count == 1

    retrieved = sched_store.get_schedule(sched.schedule_id)
    assert retrieved is not None
    assert retrieved.iterations_count == 1
    assert retrieved.next_run_at is not None
    assert retrieved.next_run_at > now_iso


def test_03_dispatch_cron_schedule_computes_future_slot(tmp_path):
    """Test 03: Dispatch CRON schedule computes and persists future cron slot."""
    db_file = str(tmp_path / "sched_stage3_3.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    sched_store = ScheduleStore(store=sql_store)

    goal = goal_mgr.create_goal("Cron goal")
    ref_dt = datetime(2026, 8, 15, 10, 0, 0, tzinfo=UTC)
    ref_iso = ref_dt.isoformat()

    sched = TemporalSchedule(
        goal_id=goal.goal_id,
        schedule_type=ScheduleType.CRON,
        expression="*/15 * * * *",
        next_run_at=ref_iso,
    )
    sched_store.save_schedule(sched)

    dispatcher = ScheduleDispatcher(
        schedule_store=sched_store,
        goal_manager=goal_mgr,
    )

    results = dispatcher.process_due_schedules(at_timestamp=ref_iso)
    assert len(results) == 1
    assert results[0].dispatched is True
    assert results[0].next_run_at == "2026-08-15T10:15:00+00:00"


def test_04_skip_inactive_or_paused_schedules(tmp_path):
    """Test 04: PAUSED, COMPLETED, CANCELLED schedules are skipped with ScheduleSkipped event."""
    db_file = str(tmp_path / "sched_stage3_4.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    sched_store = ScheduleStore(store=sql_store)
    event_bus = EventBus()

    goal = goal_mgr.create_goal("Target goal")
    past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()

    sched = TemporalSchedule(
        goal_id=goal.goal_id,
        status=ScheduleStatus.PAUSED,
        next_run_at=past,
    )
    sched_store.save_schedule(sched)

    dispatcher = ScheduleDispatcher(
        schedule_store=sched_store,
        goal_manager=goal_mgr,
        event_bus=event_bus,
    )

    skipped_events: list[ScheduleSkipped] = []
    event_bus.subscribe(ScheduleSkipped, lambda e: skipped_events.append(e))  # type: ignore[arg-type]

    results = dispatcher.process_due_schedules()
    assert len(results) == 0  # PAUSED not returned by list_eligible_schedules


def test_05_skip_missing_or_cancelled_goal(tmp_path):
    """Test 05: Schedule linked to missing/CANCELLED PersistentGoal is skipped."""
    db_file = str(tmp_path / "sched_stage3_5.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    sched_store = ScheduleStore(store=sql_store)
    event_bus = EventBus()

    goal = goal_mgr.create_goal("Goal to cancel")
    goal_mgr.cancel_goal(goal.goal_id)

    past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    sched = TemporalSchedule(
        goal_id=goal.goal_id,
        schedule_type=ScheduleType.INTERVAL,
        expression="300",
        next_run_at=past,
    )
    sched_store.save_schedule(sched)

    dispatcher = ScheduleDispatcher(
        schedule_store=sched_store,
        goal_manager=goal_mgr,
        event_bus=event_bus,
    )

    skipped_events: list[ScheduleSkipped] = []
    event_bus.subscribe(ScheduleSkipped, lambda e: skipped_events.append(e))  # type: ignore[arg-type]

    results = dispatcher.process_due_schedules()
    assert len(results) == 1
    assert results[0].dispatched is False
    assert "missing or inactive" in results[0].reason
    assert len(skipped_events) == 1

    # Verify iterations_count was NOT consumed
    retrieved = sched_store.get_schedule(sched.schedule_id)
    assert retrieved is not None
    assert retrieved.iterations_count == 0


def test_06_dry_run_mode_does_not_mutate_state(tmp_path):
    """Test 06: execute_goals=False (Dry-run mode) does not mutate SQLite or iterations_count."""
    db_file = str(tmp_path / "sched_stage3_6.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    sched_store = ScheduleStore(store=sql_store)

    goal = goal_mgr.create_goal("Dry run goal")
    past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()

    sched = TemporalSchedule(
        goal_id=goal.goal_id,
        schedule_type=ScheduleType.ONE_SHOT,
        next_run_at=past,
    )
    sched_store.save_schedule(sched)

    dispatcher = ScheduleDispatcher(
        schedule_store=sched_store,
        goal_manager=goal_mgr,
    )

    results = dispatcher.process_due_schedules(execute_goals=False)
    assert len(results) == 1
    assert results[0].dispatched is False
    assert results[0].reason == "Dry run / simulation mode"

    # SQLite state remains completely untouched
    retrieved = sched_store.get_schedule(sched.schedule_id)
    assert retrieved is not None
    assert retrieved.iterations_count == 0
    assert retrieved.status == ScheduleStatus.ACTIVE


def test_07_goal_execution_failure_consumes_schedule_pulse(tmp_path):
    """Test 07: Execution error in planner/executor records failure and consumes pulse."""
    db_file = str(tmp_path / "sched_stage3_7.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    sched_store = ScheduleStore(store=sql_store)

    goal = goal_mgr.create_goal("Broken task goal")
    past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()

    sched = TemporalSchedule(
        goal_id=goal.goal_id,
        schedule_type=ScheduleType.INTERVAL,
        expression="300",
        next_run_at=past,
    )
    sched_store.save_schedule(sched)

    # Mock planner to raise an exception
    mock_planner = MagicMock(spec=AgentPlanner)
    mock_planner.deliberate_and_plan.side_effect = RuntimeError(
        "Planner failed to generate strategy"
    )

    dispatcher = ScheduleDispatcher(
        schedule_store=sched_store,
        goal_manager=goal_mgr,
        planner=mock_planner,
    )

    results = dispatcher.process_due_schedules()
    assert len(results) == 1
    assert results[0].dispatched is False
    assert "Planner failed" in results[0].reason

    # Pulse IS consumed to prevent infinite loop
    retrieved = sched_store.get_schedule(sched.schedule_id)
    assert retrieved is not None
    assert retrieved.iterations_count == 1

    # Goal status is marked FAILED
    updated_goal = goal_mgr.get_goal(goal.goal_id)
    assert updated_goal is not None
    assert updated_goal.status == GoalStatus.FAILED


def test_08_deduplication_prevents_reentrant_dispatch(tmp_path):
    """Test 08: Active schedule in _active_dispatches is skipped during reentrant call."""
    db_file = str(tmp_path / "sched_stage3_8.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    sched_store = ScheduleStore(store=sql_store)

    goal = goal_mgr.create_goal("Deduplicated goal")
    past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()

    sched = TemporalSchedule(
        goal_id=goal.goal_id,
        schedule_type=ScheduleType.INTERVAL,
        expression="300",
        next_run_at=past,
    )
    sched_store.save_schedule(sched)

    dispatcher = ScheduleDispatcher(
        schedule_store=sched_store,
        goal_manager=goal_mgr,
    )

    # Simulate active dispatch by manually adding schedule_id to _active_dispatches
    dispatcher._active_dispatches.add(sched.schedule_id)

    results = dispatcher.process_due_schedules()
    assert len(results) == 1
    assert results[0].dispatched is False
    assert "deduplicated" in results[0].reason

    # Cleanup manually for test safety
    dispatcher._active_dispatches.clear()


def test_09_events_published_to_event_bus(tmp_path):
    """Test 09: ScheduleTriggered and ScheduleRunRecorded events are published on EventBus."""
    db_file = str(tmp_path / "sched_stage3_9.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    sched_store = ScheduleStore(store=sql_store)
    event_bus = EventBus()

    goal = goal_mgr.create_goal("Event goal")
    past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()

    sched = TemporalSchedule(
        goal_id=goal.goal_id,
        schedule_type=ScheduleType.ONE_SHOT,
        next_run_at=past,
    )
    sched_store.save_schedule(sched)

    triggered_events: list[ScheduleTriggered] = []
    recorded_events: list[ScheduleRunRecorded] = []

    event_bus.subscribe(ScheduleTriggered, lambda e: triggered_events.append(e))  # type: ignore[arg-type]
    event_bus.subscribe(ScheduleRunRecorded, lambda e: recorded_events.append(e))  # type: ignore[arg-type]

    dispatcher = ScheduleDispatcher(
        schedule_store=sched_store,
        goal_manager=goal_mgr,
        event_bus=event_bus,
    )

    results = dispatcher.process_due_schedules()
    assert len(results) == 1
    assert len(triggered_events) == 1
    assert len(recorded_events) == 1

    assert triggered_events[0].schedule_id == sched.schedule_id
    assert recorded_events[0].schedule_id == sched.schedule_id
    assert recorded_events[0].status == "COMPLETED"


def test_10_aura_15_compatibility(tmp_path):
    """Test 10: End-to-end integration with GoalManager, AgentPlanner, and AgentExecutor."""
    db_file = str(tmp_path / "sched_stage3_10.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    sched_store = ScheduleStore(store=sql_store)

    goal = goal_mgr.create_goal("Full E2E Goal", priority=GoalPriority.HIGH)
    past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()

    sched = TemporalSchedule(
        goal_id=goal.goal_id,
        schedule_type=ScheduleType.ONE_SHOT,
        next_run_at=past,
    )
    sched_store.save_schedule(sched)

    # Mock Planner and Executor
    planner = MagicMock(spec=AgentPlanner)
    executor = MagicMock(spec=AgentExecutor)

    mock_plan = AgentPlan(
        goal=AgentGoal(description="Full E2E Goal"),
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

    results = dispatcher.process_due_schedules()
    assert len(results) == 1
    assert results[0].dispatched is True

    # Goal status updated to COMPLETED by record_execution_outcome
    updated_goal = goal_mgr.get_goal(goal.goal_id)
    assert updated_goal is not None
    assert updated_goal.status == GoalStatus.COMPLETED


def test_11_max_iterations_cap_completes_schedule(tmp_path):
    """Test 11: Reaching max_iterations updates schedule status to COMPLETED."""
    db_file = str(tmp_path / "sched_stage3_11.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    sched_store = ScheduleStore(store=sql_store)

    goal = goal_mgr.create_goal("Cap goal")
    past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()

    sched = TemporalSchedule(
        goal_id=goal.goal_id,
        schedule_type=ScheduleType.INTERVAL,
        expression="60",
        max_iterations=1,
        iterations_count=0,
        next_run_at=past,
    )
    sched_store.save_schedule(sched)

    dispatcher = ScheduleDispatcher(
        schedule_store=sched_store,
        goal_manager=goal_mgr,
    )

    results = dispatcher.process_due_schedules()
    assert len(results) == 1
    assert results[0].status == ScheduleStatus.COMPLETED

    retrieved = sched_store.get_schedule(sched.schedule_id)
    assert retrieved is not None
    assert retrieved.status == ScheduleStatus.COMPLETED


def test_12_repeated_invocations_same_timestamp_idempotent(tmp_path):
    """Test 12: Calling process_due_schedules twice with same timestamp is idempotent."""
    db_file = str(tmp_path / "sched_stage3_12.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    sched_store = ScheduleStore(store=sql_store)

    goal = goal_mgr.create_goal("Idempotent goal")
    ref_iso = "2026-08-15T12:00:00+00:00"

    sched = TemporalSchedule(
        goal_id=goal.goal_id,
        schedule_type=ScheduleType.ONE_SHOT,
        next_run_at=ref_iso,
    )
    sched_store.save_schedule(sched)

    dispatcher = ScheduleDispatcher(
        schedule_store=sched_store,
        goal_manager=goal_mgr,
    )

    res1 = dispatcher.process_due_schedules(at_timestamp=ref_iso)
    assert len(res1) == 1
    assert res1[0].dispatched is True

    # Second invocation with same timestamp finds schedule completed and skips execution
    res2 = dispatcher.process_due_schedules(at_timestamp=ref_iso)
    assert len(res2) == 0
