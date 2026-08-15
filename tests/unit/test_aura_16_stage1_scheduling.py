from datetime import UTC, datetime, timedelta

import pytest

from aura.cognition.goals import GoalManager, GoalPriority, GoalStore
from aura.cognition.scheduling import ScheduleStatus, ScheduleStore, ScheduleType, TemporalSchedule
from aura.memory.store import SQLiteMemoryStore


def test_1_temporal_schedule_default_fields():
    """Test 1: TemporalSchedule initializes with valid defaults."""
    sched = TemporalSchedule(goal_id="pgoal_12345")
    assert sched.goal_id == "pgoal_12345"
    assert sched.schedule_id.startswith("sched_")
    assert sched.schedule_type == ScheduleType.ONE_SHOT
    assert sched.status == ScheduleStatus.ACTIVE
    assert sched.iterations_count == 0
    assert sched.last_run_at is None
    assert sched.next_run_at is None


def test_2_empty_goal_id_raises_error():
    """Test 2: Instantiating TemporalSchedule with empty goal_id raises ValueError."""
    with pytest.raises(ValueError, match="goal_id cannot be empty"):
        TemporalSchedule(goal_id="")


def test_3_schedule_type_enums():
    """Test 3: ScheduleType contains expected enum values."""
    assert ScheduleType.ONE_SHOT.value == "ONE_SHOT"
    assert ScheduleType.INTERVAL.value == "INTERVAL"
    assert ScheduleType.CRON.value == "CRON"
    assert ScheduleType.CONTINUOUS.value == "CONTINUOUS"


def test_4_schedule_status_enums():
    """Test 4: ScheduleStatus contains expected enum values."""
    assert ScheduleStatus.ACTIVE.value == "ACTIVE"
    assert ScheduleStatus.PAUSED.value == "PAUSED"
    assert ScheduleStatus.COMPLETED.value == "COMPLETED"
    assert ScheduleStatus.CANCELLED.value == "CANCELLED"


def test_5_status_transition_updates_timestamp():
    """Test 5: set_status updates status and updated_at timestamp."""
    sched = TemporalSchedule(goal_id="pgoal_12345")
    orig_updated = sched.updated_at

    sched.set_status(ScheduleStatus.PAUSED)
    assert sched.status == ScheduleStatus.PAUSED
    assert sched.updated_at >= orig_updated


def test_6_is_eligible_status_checks():
    """Test 6: is_eligible returns False for PAUSED, COMPLETED, CANCELLED statuses."""
    sched = TemporalSchedule(goal_id="pgoal_12345", status=ScheduleStatus.ACTIVE)
    assert sched.is_eligible() is True

    sched.status = ScheduleStatus.PAUSED
    assert sched.is_eligible() is False

    sched.status = ScheduleStatus.COMPLETED
    assert sched.is_eligible() is False

    sched.status = ScheduleStatus.CANCELLED
    assert sched.is_eligible() is False


def test_7_continuous_schedule_always_eligible_when_active():
    """Test 7: CONTINUOUS schedule type is always eligible when status is ACTIVE."""
    sched = TemporalSchedule(
        goal_id="pgoal_12345",
        schedule_type=ScheduleType.CONTINUOUS,
        status=ScheduleStatus.ACTIVE,
    )
    assert sched.is_eligible() is True


def test_8_one_shot_eligibility_timestamp_comparison():
    """Test 8: ONE_SHOT schedule compares next_run_at against target timestamp."""
    now = datetime.now(UTC)
    past = (now - timedelta(minutes=10)).isoformat()
    future = (now + timedelta(minutes=10)).isoformat()

    sched_past = TemporalSchedule(
        goal_id="pgoal_1",
        schedule_type=ScheduleType.ONE_SHOT,
        next_run_at=past,
    )
    assert sched_past.is_eligible(at_timestamp=now.isoformat()) is True

    sched_future = TemporalSchedule(
        goal_id="pgoal_2",
        schedule_type=ScheduleType.ONE_SHOT,
        next_run_at=future,
    )
    assert sched_future.is_eligible(at_timestamp=now.isoformat()) is False


def test_9_record_run_updates_state_and_completes_oneshot():
    """Test 9: record_run updates last_run_at, increments count, and completes ONE_SHOT."""
    sched = TemporalSchedule(
        goal_id="pgoal_12345",
        schedule_type=ScheduleType.ONE_SHOT,
    )
    assert sched.iterations_count == 0

    sched.record_run()
    assert sched.iterations_count == 1
    assert sched.last_run_at is not None
    assert sched.status == ScheduleStatus.COMPLETED


def test_10_record_run_respects_max_iterations():
    """Test 10: record_run transitions status to COMPLETED when max_iterations reached."""
    sched = TemporalSchedule(
        goal_id="pgoal_12345",
        schedule_type=ScheduleType.INTERVAL,
        expression="60",
        max_iterations=2,
    )

    sched.record_run()
    assert sched.iterations_count == 1
    assert sched.status == ScheduleStatus.ACTIVE

    sched.record_run()
    assert sched.iterations_count == 2
    assert sched.status == ScheduleStatus.COMPLETED


def test_11_record_run_idempotent_on_terminal_status():
    """Test 11: record_run is idempotent on COMPLETED or CANCELLED schedules."""
    sched = TemporalSchedule(
        goal_id="pgoal_12345",
        status=ScheduleStatus.COMPLETED,
        iterations_count=1,
    )

    sched.record_run()
    assert sched.iterations_count == 1


def test_12_store_initialization(tmp_path):
    """Test 12: ScheduleStore initializes SQLite table and indexes cleanly."""
    db_file = str(tmp_path / "sched_test_12.db")
    store = ScheduleStore(db_path=db_file)

    conn = store._get_connection()
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='temporal_schedules'"
    )
    assert cursor.fetchone() is not None


def test_13_save_and_get_schedule(tmp_path):
    """Test 13: ScheduleStore saves and retrieves TemporalSchedule accurately."""
    db_file = str(tmp_path / "sched_test_13.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    store = ScheduleStore(store=sql_store)

    goal = goal_mgr.create_goal("Target goal", priority=GoalPriority.MEDIUM)

    sched = TemporalSchedule(
        goal_id=goal.goal_id,
        schedule_type=ScheduleType.INTERVAL,
        expression="300",
        metadata={"note": "Every 5 min"},
    )
    store.save_schedule(sched)

    retrieved = store.get_schedule(sched.schedule_id)
    assert retrieved is not None
    assert retrieved.schedule_id == sched.schedule_id
    assert retrieved.goal_id == goal.goal_id
    assert retrieved.schedule_type == ScheduleType.INTERVAL
    assert retrieved.expression == "300"
    assert retrieved.metadata.get("note") == "Every 5 min"


def test_14_list_schedules_filters(tmp_path):
    """Test 14: ScheduleStore list_schedules filters by goal_id, status, schedule_type."""
    db_file = str(tmp_path / "sched_test_14.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    store = ScheduleStore(store=sql_store)

    g1 = goal_mgr.create_goal("Goal 1", priority=GoalPriority.HIGH)
    g2 = goal_mgr.create_goal("Goal 2", priority=GoalPriority.LOW)

    s1 = TemporalSchedule(
        goal_id=g1.goal_id, schedule_type=ScheduleType.ONE_SHOT, status=ScheduleStatus.ACTIVE
    )
    s2 = TemporalSchedule(
        goal_id=g1.goal_id, schedule_type=ScheduleType.INTERVAL, status=ScheduleStatus.PAUSED
    )
    s3 = TemporalSchedule(
        goal_id=g2.goal_id, schedule_type=ScheduleType.CRON, status=ScheduleStatus.ACTIVE
    )

    store.save_schedule(s1)
    store.save_schedule(s2)
    store.save_schedule(s3)

    g1_list = store.list_schedules(goal_id=g1.goal_id)
    assert len(g1_list) == 2

    paused_list = store.list_schedules(status=ScheduleStatus.PAUSED)
    assert len(paused_list) == 1
    assert paused_list[0].schedule_id == s2.schedule_id

    cron_list = store.list_schedules(schedule_type=ScheduleType.CRON)
    assert len(cron_list) == 1
    assert cron_list[0].schedule_id == s3.schedule_id


def test_15_list_eligible_schedules(tmp_path):
    """Test 15: list_eligible_schedules returns only active, time-eligible schedules."""
    db_file = str(tmp_path / "sched_test_15.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    store = ScheduleStore(store=sql_store)

    g1 = goal_mgr.create_goal("G1", priority=GoalPriority.HIGH)
    g2 = goal_mgr.create_goal("G2", priority=GoalPriority.MEDIUM)
    g3 = goal_mgr.create_goal("G3", priority=GoalPriority.LOW)

    now = datetime.now(UTC)
    past = (now - timedelta(minutes=5)).isoformat()
    future = (now + timedelta(minutes=5)).isoformat()

    s_eligible = TemporalSchedule(
        goal_id=g1.goal_id, schedule_type=ScheduleType.ONE_SHOT, next_run_at=past
    )
    s_future = TemporalSchedule(
        goal_id=g2.goal_id, schedule_type=ScheduleType.ONE_SHOT, next_run_at=future
    )
    s_paused = TemporalSchedule(
        goal_id=g3.goal_id,
        schedule_type=ScheduleType.CONTINUOUS,
        status=ScheduleStatus.PAUSED,
    )

    store.save_schedule(s_eligible)
    store.save_schedule(s_future)
    store.save_schedule(s_paused)

    eligible = store.list_eligible_schedules(at_timestamp=now.isoformat())
    assert len(eligible) == 1
    assert eligible[0].schedule_id == s_eligible.schedule_id


def test_16_delete_schedule(tmp_path):
    """Test 16: ScheduleStore delete_schedule removes row physically."""
    db_file = str(tmp_path / "sched_test_16.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    store = ScheduleStore(store=sql_store)

    goal = goal_mgr.create_goal("Goal to delete schedule for")
    sched = TemporalSchedule(goal_id=goal.goal_id)
    store.save_schedule(sched)
    assert store.get_schedule(sched.schedule_id) is not None

    deleted = store.delete_schedule(sched.schedule_id)
    assert deleted is True
    assert store.get_schedule(sched.schedule_id) is None


def test_17_corrupt_row_handling(tmp_path):
    """Test 17: ScheduleStore fallback logic handles corrupt metadata or enum fields safely."""
    db_file = str(tmp_path / "sched_test_17.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    store = ScheduleStore(store=sql_store)

    goal = goal_mgr.create_goal("Corrupt row goal")

    conn = store._get_connection()
    with conn:
        conn.execute(
            """
            INSERT INTO temporal_schedules (
                schedule_id, goal_id, schedule_type, status, expression,
                created_at, updated_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "sched_corrupt",
                goal.goal_id,
                "INVALID_TYPE",
                "BAD_STATUS",
                "",
                "2026-08-15T00:00:00Z",
                "2026-08-15T00:00:00Z",
                "INVALID_JSON",
            ),
        )

    retrieved = store.get_schedule("sched_corrupt")
    assert retrieved is not None
    assert retrieved.schedule_type == ScheduleType.ONE_SHOT
    assert retrieved.status == ScheduleStatus.ACTIVE
    assert retrieved.metadata == {}


def test_18_thread_lock_sharing(tmp_path):
    """Test 18: ScheduleStore reuses SQLiteMemoryStore connection lock correctly."""
    db_file = str(tmp_path / "sched_test_18.db")
    mem_store = SQLiteMemoryStore(db_path=db_file)
    sched_store = ScheduleStore(store=mem_store)

    assert sched_store._lock is mem_store._lock


def test_19_goal_association(tmp_path):
    """Test 19: TemporalSchedule goal_id links correctly to a PersistentGoal in SQLite."""
    db_file = str(tmp_path / "sched_test_19.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)

    goal_store = GoalStore(store=sql_store)
    goal_mgr = GoalManager(store=goal_store)
    sched_store = ScheduleStore(store=sql_store)

    goal = goal_mgr.create_goal("Scheduled goal", priority=GoalPriority.HIGH)
    sched = TemporalSchedule(
        goal_id=goal.goal_id,
        schedule_type=ScheduleType.INTERVAL,
        expression="300",
    )
    sched_store.save_schedule(sched)

    schedules_for_goal = sched_store.list_schedules(goal_id=goal.goal_id)
    assert len(schedules_for_goal) == 1
    assert schedules_for_goal[0].goal_id == goal.goal_id


def test_20_aura_15_no_side_effects(tmp_path):
    """Test 20: Instantiating ScheduleStore has zero side-effects on AURA 1.5 goal execution."""
    db_file = str(tmp_path / "sched_test_20.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)

    goal_store = GoalStore(store=sql_store)
    goal_mgr = GoalManager(store=goal_store)
    sched_store = ScheduleStore(store=sql_store)

    g1 = goal_mgr.create_goal("Goal 1", priority=GoalPriority.HIGH)
    sched = TemporalSchedule(goal_id=g1.goal_id)
    sched_store.save_schedule(sched)

    # Goal lifecycle functions normally without background threads or scheduler runtimes
    assert goal_mgr.get_goal(g1.goal_id).status.value == "PENDING"


def test_21_invalid_iterations_raises_error():
    """Test 21: Negative iterations_count or max_iterations < 1 raises ValueError."""
    with pytest.raises(ValueError, match="iterations_count cannot be negative"):
        TemporalSchedule(goal_id="g1", iterations_count=-1)

    with pytest.raises(ValueError, match="max_iterations must be at least 1"):
        TemporalSchedule(goal_id="g1", max_iterations=0)


def test_22_record_run_on_paused_schedule_is_no_op():
    """Test 22: record_run on PAUSED schedule is a no-op and does not increment iterations_count."""
    sched = TemporalSchedule(goal_id="g1", status=ScheduleStatus.PAUSED, iterations_count=0)
    sched.record_run()
    assert sched.iterations_count == 0
    assert sched.status == ScheduleStatus.PAUSED


def test_23_timestamp_normalization():
    """Test 23: Naïve and timezone-aware ISO timestamps are normalized to UTC ISO strings."""
    sched = TemporalSchedule(
        goal_id="g1",
        created_at="2026-08-15T00:00:00",  # naïve
        next_run_at="2026-08-15T00:00:00+00:00",  # aware
    )
    assert "+00:00" in sched.created_at or "Z" in sched.created_at
    assert "+00:00" in sched.next_run_at or "Z" in sched.next_run_at


def test_24_cascade_delete_goal_removes_schedule(tmp_path):
    """Test 24: Deleting a PersistentGoal CASCADE deletes associated TemporalSchedule in SQLite."""
    db_file = str(tmp_path / "sched_test_24.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)

    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    sched_store = ScheduleStore(store=sql_store)

    goal = goal_mgr.create_goal("Goal to cascade delete")
    sched = TemporalSchedule(goal_id=goal.goal_id)
    sched_store.save_schedule(sched)

    assert sched_store.get_schedule(sched.schedule_id) is not None

    # Delete PersistentGoal
    goal_mgr.delete_goal(goal.goal_id)

    # Schedule is CASCADE deleted from SQLite
    assert sched_store.get_schedule(sched.schedule_id) is None
