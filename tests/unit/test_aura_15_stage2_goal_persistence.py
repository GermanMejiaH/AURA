from __future__ import annotations

import pytest

from aura.cognition.deliberation.models import GoalModel, RiskLevel
from aura.cognition.goals import (
    GoalContextRef,
    GoalManager,
    GoalPriority,
    GoalProgress,
    GoalStatus,
    GoalStore,
    PersistentGoal,
)
from aura.events import (
    EventBus,
    GoalProgressUpdated,
    GoalStatusChanged,
    GoalUpdated,
)
from aura.memory.store import SQLiteMemoryStore


@pytest.fixture
def temp_store(tmp_path):
    db_file = str(tmp_path / "test_stage2.db")
    mem_store = SQLiteMemoryStore(db_path=db_file)
    store = GoalStore(store=mem_store)
    return store


@pytest.fixture
def temp_manager(temp_store):
    bus = EventBus()
    mgr = GoalManager(store=temp_store, event_bus=bus)
    return mgr, bus


def test_1_create_and_retrieve_goal(temp_store):
    """Test 1 & 2: Create a PersistentGoal and retrieve by ID."""
    goal = PersistentGoal(description="Clean workshop", priority=GoalPriority.HIGH)
    temp_store.save_goal(goal)

    retrieved = temp_store.get_goal(goal.goal_id)
    assert retrieved is not None
    assert retrieved.goal_id == goal.goal_id
    assert retrieved.description == "Clean workshop"
    assert retrieved.priority == GoalPriority.HIGH


def test_3_nonexistent_goal_returns_none(temp_store):
    """Test 3: get_goal with nonexistent ID returns None."""
    assert temp_store.get_goal("nonexistent_id_999") is None


def test_4_full_field_round_trip_persistence(temp_store):
    """Test 4 & 12: All fields survive round-trip SQLite serialization."""
    ctx = GoalContextRef(
        location="lab_room",
        entities=["robot_arm", "camera"],
        tags=["hardware", "maintenance"],
        metadata={"priority_score": 95.5},
    )
    prog = GoalProgress(
        completion_percentage=45.0,
        milestones_completed=["calibrated", "tested"],
        notes="All green",
    )
    goal = PersistentGoal(
        description="Calibrate actuators",
        priority=GoalPriority.CRITICAL,
        status=GoalStatus.ACTIVE,
        success_criteria=["error_margin < 0.1mm"],
        constraints=["no_collision"],
        context=ctx,
        progress=prog,
        parent_goal_id="parent_001",
        risk_tolerance=RiskLevel.LOW,
    )
    temp_store.save_goal(goal)

    fetched = temp_store.get_goal(goal.goal_id)
    assert fetched is not None
    assert fetched.description == "Calibrate actuators"
    assert fetched.priority == GoalPriority.CRITICAL
    assert fetched.status == GoalStatus.ACTIVE
    assert fetched.success_criteria == ["error_margin < 0.1mm"]
    assert fetched.constraints == ["no_collision"]
    assert fetched.context.location == "lab_room"
    assert "robot_arm" in fetched.context.entities
    assert fetched.context.metadata["priority_score"] == 95.5
    assert fetched.progress.completion_percentage == 45.0
    assert "calibrated" in fetched.progress.milestones_completed
    assert fetched.parent_goal_id == "parent_001"
    assert fetched.risk_tolerance == RiskLevel.LOW


def test_5_update_goal_fields_and_timestamp(temp_manager):
    """Test 5 & 6: Update goal fields and verify updated_at timestamp updates."""
    mgr, bus = temp_manager
    events = []
    bus.subscribe("*", lambda e: events.append(e))

    goal = mgr.create_goal("Original title", priority=GoalPriority.LOW)
    orig_updated = goal.updated_at

    updated = mgr.update_goal(
        goal.goal_id,
        description="Updated title",
        priority=GoalPriority.HIGH,
        constraints=["new_constraint"],
    )

    assert updated.description == "Updated title"
    assert updated.priority == GoalPriority.HIGH
    assert "new_constraint" in updated.constraints
    assert updated.updated_at >= orig_updated
    assert any(isinstance(e, GoalUpdated) for e in events)


def test_7_change_status(temp_manager):
    """Test 7 & 19: Change status publishes GoalStatusChanged event."""
    mgr, bus = temp_manager
    events = []
    bus.subscribe("*", lambda e: events.append(e))

    goal = mgr.create_goal("Status test goal")
    updated = mgr.set_status(goal.goal_id, GoalStatus.ACTIVE)

    assert updated.status == GoalStatus.ACTIVE
    assert any(
        isinstance(e, GoalStatusChanged) and e.old_status == "PENDING" and e.new_status == "ACTIVE"
        for e in events
    )


def test_8_update_progress(temp_manager):
    """Test 8: GoalProgress updates correctly and fires GoalProgressUpdated event."""
    mgr, bus = temp_manager
    events = []
    bus.subscribe("*", lambda e: events.append(e))

    goal = mgr.create_goal("Progress goal")
    updated = mgr.update_progress(
        goal.goal_id, percentage=75.0, add_milestone="Step 1 complete", notes="Good pace"
    )

    assert updated.progress.completion_percentage == 75.0
    assert "Step 1 complete" in updated.progress.milestones_completed
    assert any(
        isinstance(e, GoalProgressUpdated)
        and e.completion_percentage == 75.0
        and e.milestone_added == "Step 1 complete"
        for e in events
    )


def test_9_filtering_by_status(temp_store):
    """Test 9: list_goals filters by status."""
    g1 = PersistentGoal(description="G1", status=GoalStatus.PENDING)
    g2 = PersistentGoal(description="G2", status=GoalStatus.ACTIVE)
    g3 = PersistentGoal(description="G3", status=GoalStatus.COMPLETED)
    temp_store.save_goal(g1)
    temp_store.save_goal(g2)
    temp_store.save_goal(g3)

    active_goals = temp_store.list_goals(status=GoalStatus.ACTIVE)
    assert len(active_goals) == 1
    assert active_goals[0].goal_id == g2.goal_id


def test_10_filtering_by_priority(temp_store):
    """Test 10: list_goals filters by priority."""
    g1 = PersistentGoal(description="G1", priority=GoalPriority.LOW)
    g2 = PersistentGoal(description="G2", priority=GoalPriority.CRITICAL)
    temp_store.save_goal(g1)
    temp_store.save_goal(g2)

    crit_goals = temp_store.list_goals(priority=GoalPriority.CRITICAL)
    assert len(crit_goals) == 1
    assert crit_goals[0].goal_id == g2.goal_id


def test_11_filtering_by_parent_goal_id(temp_store):
    """Test 11: list_goals filters by parent_goal_id."""
    parent = PersistentGoal(description="Parent Goal")
    child1 = PersistentGoal(description="Child 1", parent_goal_id=parent.goal_id)
    child2 = PersistentGoal(description="Child 2", parent_goal_id=parent.goal_id)
    other = PersistentGoal(description="Unrelated")

    temp_store.save_goal(parent)
    temp_store.save_goal(child1)
    temp_store.save_goal(child2)
    temp_store.save_goal(other)

    children = temp_store.list_goals(parent_goal_id=parent.goal_id)
    assert len(children) == 2
    assert {c.goal_id for c in children} == {child1.goal_id, child2.goal_id}


def test_13_corrupted_json_fallback_handling(temp_store):
    """Test 13: Corrupted JSON strings in database fallback to safe defaults."""
    conn = temp_store._get_connection()
    with conn:
        conn.execute(
            """
            INSERT INTO persistent_goals (
                goal_id, description, priority, status, created_at, updated_at,
                success_criteria_json, constraints_json, context_json, progress_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "corrupt_01",
                "Corrupt row test",
                "INVALID_PRIORITY",
                "INVALID_STATUS",
                "2026-01-01T00:00:00",
                "2026-01-01T00:00:00",
                "{invalid_json",
                "{invalid_json",
                "{invalid_json",
                "{invalid_json",
            ),
        )

    retrieved = temp_store.get_goal("corrupt_01")
    assert retrieved is not None
    assert retrieved.priority == GoalPriority.MEDIUM
    assert retrieved.status == GoalStatus.PENDING
    assert retrieved.success_criteria == []
    assert retrieved.constraints == []


def test_14_duplicate_id_upsert(temp_store):
    """Test 14: Saving goal with existing ID replaces/upserts cleanly."""
    goal = PersistentGoal(description="Initial version")
    temp_store.save_goal(goal)

    goal.description = "Updated version"
    temp_store.save_goal(goal)

    retrieved = temp_store.get_goal(goal.goal_id)
    assert retrieved is not None
    assert retrieved.description == "Updated version"


def test_15_thread_safety_locking(temp_store):
    """Test 15: Thread safety using internal RLock."""
    assert temp_store._lock is not None
    goal = PersistentGoal(description="Locking test")
    with temp_store._lock:
        temp_store.save_goal(goal)
    assert temp_store.get_goal(goal.goal_id) is not None


def test_16_atomic_transactions(temp_store):
    """Test 16 & 17: Database transaction commits atomically or rolls back on failure."""
    conn = temp_store._get_connection()
    goal = PersistentGoal(description="Tx test")

    try:
        with conn:
            conn.execute(
                "INSERT INTO persistent_goals "
                "(goal_id, description, priority, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    goal.goal_id,
                    goal.description,
                    "MEDIUM",
                    "PENDING",
                    goal.created_at,
                    goal.updated_at,
                ),
            )
            raise RuntimeError("Force abort transaction")  # noqa: TRY301
    except RuntimeError:
        pass

    assert temp_store.get_goal(goal.goal_id) is None


def test_18_logical_cancel_and_physical_delete(temp_manager):
    """Test 18: Logical cancellation sets CANCELLED status, physical deletion removes row."""
    mgr, _ = temp_manager
    g1 = mgr.create_goal("Logical cancel target")
    g2 = mgr.create_goal("Physical delete target")

    cancelled = mgr.cancel_goal(g1.goal_id)
    assert cancelled.status == GoalStatus.CANCELLED
    assert mgr.get_goal(g1.goal_id) is not None

    deleted = mgr.delete_goal(g2.goal_id)
    assert deleted is True
    assert mgr.get_goal(g2.goal_id) is None


def test_20_no_event_published_on_no_op_status(temp_manager):
    """Test 20: No event is published if status change is a no-op."""
    mgr, bus = temp_manager
    events = []
    bus.subscribe("*", lambda e: events.append(e))

    goal = mgr.create_goal("No-op test")
    events.clear()

    mgr.set_status(goal.goal_id, GoalStatus.PENDING)
    assert len(events) == 0


def test_21_input_object_unmutated_on_save(temp_store):
    """Test 21: PersistentGoal input object is not mutated by save_goal."""
    goal = PersistentGoal(description="Unmutated object test")
    goal_id_before = goal.goal_id
    status_before = goal.status

    temp_store.save_goal(goal)

    assert goal.goal_id == goal_id_before
    assert goal.status == status_before


def test_22_goal_model_projection_integrity(temp_manager):
    """Test 22: PersistentGoal from GoalManager projects cleanly into AURA 1.4 GoalModel."""
    mgr, _ = temp_manager
    pgoal = mgr.create_goal(
        "Deploy application stack",
        priority=GoalPriority.HIGH,
        constraints=["no_downtime"],
        success_criteria=["all_services_healthy"],
        risk_tolerance=RiskLevel.LOW,
    )

    gmodel = pgoal.to_goal_model()
    assert isinstance(gmodel, GoalModel)
    assert gmodel.goal_id == pgoal.goal_id
    assert gmodel.description == "Deploy application stack"
    assert gmodel.priority == 3.0
    assert gmodel.constraints == ["no_downtime"]
    assert gmodel.success_criteria == ["all_services_healthy"]
    assert gmodel.risk_tolerance == RiskLevel.LOW


def test_23_legacy_schema_compatibility(temp_store):
    """Test 23: Store reads row created without optional JSON columns cleanly."""
    conn = temp_store._get_connection()
    with conn:
        conn.execute(
            """
            INSERT INTO persistent_goals (
                goal_id, description, priority, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy_pgoal_01",
                "Legacy goal row",
                "HIGH",
                "PENDING",
                "2026-01-01T00:00:00",
                "2026-01-01T00:00:00",
            ),
        )

    retrieved = temp_store.get_goal("legacy_pgoal_01")
    assert retrieved is not None
    assert retrieved.goal_id == "legacy_pgoal_01"
    assert retrieved.priority == GoalPriority.HIGH


def test_24_deterministic_sorting(temp_store):
    """Test 24: list_goals returns goals sorted deterministically by created_at ASC."""
    g1 = PersistentGoal(description="First", created_at="2026-01-01T10:00:00Z")
    g2 = PersistentGoal(description="Second", created_at="2026-01-01T11:00:00Z")
    temp_store.save_goal(g2)
    temp_store.save_goal(g1)

    goals = temp_store.list_goals()
    assert len(goals) == 2
    assert goals[0].description == "First"
    assert goals[1].description == "Second"
