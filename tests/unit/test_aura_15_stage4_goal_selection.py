from __future__ import annotations

from aura.autonomy.planner import AgentPlanner
from aura.cognition.context import CognitiveContextBuilder
from aura.cognition.goals import (
    GoalManager,
    GoalPrioritizer,
    GoalPriority,
    GoalSelector,
    GoalStatus,
    GoalStore,
    PersistentGoal,
    SelectedGoal,
)
from aura.container import DependencyContainer
from aura.events import EventBus, GoalSelectedForExecution


def test_1_selection_of_eligible_goal():
    """Test 1: GoalSelector selects an ACTIVE or PENDING goal."""
    g = PersistentGoal(description="Eligible goal", status=GoalStatus.ACTIVE)
    prioritizer = GoalPrioritizer()
    prioritized = prioritizer.prioritize([g])

    selector = GoalSelector()
    selected = selector.select_goal(prioritized)

    assert selected is not None
    assert selected.goal.goal_id == g.goal_id
    assert selected.rank == 1


def test_2_highest_priority_wins():
    """Test 2: GoalSelector selects the top ranked eligible goal."""
    g_low = PersistentGoal(
        description="Low goal", priority=GoalPriority.LOW, status=GoalStatus.ACTIVE
    )
    g_high = PersistentGoal(
        description="High goal", priority=GoalPriority.HIGH, status=GoalStatus.ACTIVE
    )

    prioritizer = GoalPrioritizer()
    prioritized = prioritizer.prioritize([g_low, g_high])

    selector = GoalSelector()
    selected = selector.select_goal(prioritized)

    assert selected is not None
    assert selected.goal.goal_id == g_high.goal_id


def test_3_deterministic_tie_breaking():
    """Test 3: Equal score goals select deterministically according to GoalPrioritizer ranking."""
    g1 = PersistentGoal(description="G1", created_at="2026-01-01T10:00:00Z", goal_id="pgoal_aaa")
    g2 = PersistentGoal(description="G2", created_at="2026-01-01T10:00:00Z", goal_id="pgoal_bbb")

    prioritizer = GoalPrioritizer()
    prioritized = prioritizer.prioritize([g2, g1])

    selector = GoalSelector()
    selected = selector.select_goal(prioritized)

    assert selected is not None
    assert selected.goal.goal_id == "pgoal_aaa"


def test_4_completed_not_eligible():
    """Test 4: COMPLETED goals are skipped during selection."""
    g = PersistentGoal(description="Done", status=GoalStatus.COMPLETED)
    prioritizer = GoalPrioritizer()
    prioritized = prioritizer.prioritize([g])

    selector = GoalSelector()
    assert selector.select_goal(prioritized) is None


def test_5_failed_not_eligible():
    """Test 5: FAILED goals are skipped during selection."""
    g = PersistentGoal(description="Failed", status=GoalStatus.FAILED)
    prioritizer = GoalPrioritizer()
    prioritized = prioritizer.prioritize([g])

    selector = GoalSelector()
    assert selector.select_goal(prioritized) is None


def test_6_cancelled_not_eligible():
    """Test 6: CANCELLED goals are skipped during selection."""
    g = PersistentGoal(description="Cancelled", status=GoalStatus.CANCELLED)
    prioritizer = GoalPrioritizer()
    prioritized = prioritizer.prioritize([g])

    selector = GoalSelector()
    assert selector.select_goal(prioritized) is None


def test_7_paused_not_eligible():
    """Test 7: PAUSED goals are skipped during automatic selection."""
    g = PersistentGoal(description="Paused", status=GoalStatus.PAUSED)
    prioritizer = GoalPrioritizer()
    prioritized = prioritizer.prioritize([g])

    selector = GoalSelector()
    assert selector.select_goal(prioritized) is None


def test_8_blocked_not_eligible_by_default():
    """Test 8: BLOCKED goals are skipped during automatic selection."""
    g = PersistentGoal(description="Blocked", status=GoalStatus.BLOCKED)
    prioritizer = GoalPrioritizer()
    prioritized = prioritizer.prioritize([g])

    selector = GoalSelector()
    assert selector.select_goal(prioritized) is None


def test_9_pending_eligible():
    """Test 9: PENDING goals are eligible for selection."""
    g = PersistentGoal(description="Pending", status=GoalStatus.PENDING)
    prioritizer = GoalPrioritizer()
    prioritized = prioritizer.prioritize([g])

    selector = GoalSelector()
    selected = selector.select_goal(prioritized)
    assert selected is not None
    assert selected.goal.goal_id == g.goal_id


def test_10_active_eligible():
    """Test 10: ACTIVE goals are eligible for selection."""
    g = PersistentGoal(description="Active", status=GoalStatus.ACTIVE)
    prioritizer = GoalPrioritizer()
    prioritized = prioritizer.prioritize([g])

    selector = GoalSelector()
    selected = selector.select_goal(prioritized)
    assert selected is not None
    assert selected.goal.goal_id == g.goal_id


def test_11_empty_list_returns_none():
    """Test 11: Empty prioritizer list returns None without raising an exception."""
    selector = GoalSelector()
    assert selector.select_goal([]) is None


def test_12_all_ineligible_returns_none():
    """Test 12: List containing only ineligible goals returns None cleanly."""
    g1 = PersistentGoal(description="G1", status=GoalStatus.COMPLETED)
    g2 = PersistentGoal(description="G2", status=GoalStatus.CANCELLED)

    prioritizer = GoalPrioritizer()
    prioritized = prioritizer.prioritize([g1, g2])

    selector = GoalSelector()
    assert selector.select_goal(prioritized) is None


def test_13_selector_does_not_mutate_goals():
    """Test 13: GoalSelector does not alter PersistentGoal attributes."""
    g = PersistentGoal(description="Unmutated", status=GoalStatus.ACTIVE)
    orig_status = g.status

    prioritizer = GoalPrioritizer()
    prioritized = prioritizer.prioritize([g])

    selector = GoalSelector()
    selector.select_goal(prioritized)

    assert g.status == orig_status


def test_14_selector_deterministic():
    """Test 14: Repeated selection yields identical SelectedGoal output."""
    g1 = PersistentGoal(description="G1", priority=GoalPriority.HIGH)
    g2 = PersistentGoal(description="G2", priority=GoalPriority.LOW)

    prioritizer = GoalPrioritizer()
    prioritized = prioritizer.prioritize([g1, g2])

    selector = GoalSelector()
    s1 = selector.select_goal(prioritized)
    s2 = selector.select_goal(prioritized)

    assert s1 is not None and s2 is not None
    assert s1.goal.goal_id == s2.goal.goal_id
    assert s1.selection_reason == s2.selection_reason


def test_15_selection_reason_reproducible():
    """Test 15: Selection reason contains clear human-readable details."""
    g = PersistentGoal(
        description="Reason test", priority=GoalPriority.HIGH, status=GoalStatus.ACTIVE
    )
    prioritizer = GoalPrioritizer()
    prioritized = prioritizer.prioritize([g])

    selector = GoalSelector()
    selected = selector.select_goal(prioritized)

    assert selected is not None
    assert "Selected rank #1" in selected.selection_reason
    assert "Reason test" in selected.selection_reason


def test_16_integration_with_goal_manager(tmp_path):
    """Test 16: GoalSelector consumes goals directly from GoalManager and GoalStore."""
    db_file = str(tmp_path / "test_stage4_mgr.db")
    store = GoalStore(db_path=db_file)
    mgr = GoalManager(store=store)

    mgr.create_goal("Task A", priority=GoalPriority.LOW)
    mgr.create_goal("Task B", priority=GoalPriority.HIGH)

    all_goals = mgr.list_goals()
    prioritizer = GoalPrioritizer()
    prioritized = prioritizer.prioritize(all_goals)

    selector = GoalSelector()
    selected = selector.select_goal(prioritized)

    assert selected is not None
    assert selected.goal.description == "Task B"


def test_17_integration_with_cognitive_context(tmp_path):
    """Test 17: SelectedGoal matches top item in CognitiveContext.prioritized_goals."""
    db_file = str(tmp_path / "test_stage4_ctx.db")
    store = GoalStore(db_path=db_file)
    mgr = GoalManager(store=store)

    mgr.create_goal("Urgent Task", priority=GoalPriority.CRITICAL)

    container = DependencyContainer()
    container.register(GoalManager, instance=mgr)

    builder = CognitiveContextBuilder(container=container)
    ctx = builder.build(input_text="Check goals")

    selector = GoalSelector()
    selected = selector.select_goal(ctx.prioritized_goals)

    assert selected is not None
    assert selected.goal.description == "Urgent Task"


def test_18_integration_with_goal_model():
    """Test 18: PersistentGoal inside SelectedGoal converts cleanly to GoalModel."""
    g = PersistentGoal(
        description="Convert model test",
        priority=GoalPriority.CRITICAL,
        constraints=["c1"],
        success_criteria=["s1"],
    )
    prioritizer = GoalPrioritizer()
    prioritized = prioritizer.prioritize([g])

    selector = GoalSelector()
    selected = selector.select_goal(prioritized)

    assert selected is not None
    gm = selected.goal.to_goal_model()
    assert gm.goal_id == g.goal_id
    assert gm.description == g.description
    assert gm.priority == 4.0
    assert gm.constraints == ["c1"]
    assert gm.success_criteria == ["s1"]


def test_19_integration_with_deliberation_engine():
    """Test 19: AgentPlanner.plan_next_goal generates AgentPlan using DeliberationEngine."""
    planner = AgentPlanner()
    g = PersistentGoal(description="Clean workshop", priority=GoalPriority.HIGH)

    prioritizer = GoalPrioritizer()
    prioritized = prioritizer.prioritize([g])

    selector = GoalSelector()
    selected = selector.select_goal(prioritized)

    assert selected is not None
    gm = selected.goal.to_goal_model()

    selection, plan = planner.deliberate_and_plan(gm)
    assert selection is not None
    assert plan is not None
    assert plan.goal.description == "Clean workshop"


def test_20_e2e_agency_pipeline(tmp_path):
    """Test 20: Full E2E pipeline from PersistentGoal to AgentPlan."""
    db_file = str(tmp_path / "test_stage4_e2e.db")
    store = GoalStore(db_path=db_file)
    mgr = GoalManager(store=store)
    bus = EventBus()

    received_events = []
    bus.subscribe(GoalSelectedForExecution, lambda e: received_events.append(e))

    mgr.create_goal("Low priority backlog", priority=GoalPriority.LOW)
    mgr.create_goal("High priority operational goal", priority=GoalPriority.HIGH)

    planner = AgentPlanner(event_bus=bus)
    result = planner.plan_next_goal(goal_manager=mgr)

    assert result is not None
    selected, _selection, plan = result

    assert isinstance(selected, SelectedGoal)
    assert selected.goal.description == "High priority operational goal"
    assert len(plan.tasks) > 0
    assert len(received_events) == 1
    assert received_events[0].goal_id == selected.goal.goal_id


def test_21_create_plan_backward_compatibility():
    """Test 21: Existing create_plan method remains fully backward-compatible."""
    from aura.cognition.deliberation import DeliberationEngine

    planner = AgentPlanner(deliberator=DeliberationEngine())
    plan = planner.create_plan("Manual goal test")
    assert plan is not None
    assert plan.goal.description == "Manual goal test"
