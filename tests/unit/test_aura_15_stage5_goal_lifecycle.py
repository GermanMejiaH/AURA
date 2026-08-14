from aura.autonomy.agent_models import AgentGoal, AgentPlan, AgentTask, TaskStatus
from aura.autonomy.executor import AgentExecutionResult, AgentExecutor
from aura.autonomy.planner import AgentPlanner
from aura.cognition.deliberation import DeliberationEngine
from aura.cognition.goals import (
    GoalManager,
    GoalPrioritizer,
    GoalPriority,
    GoalSelector,
    GoalStatus,
    GoalStore,
)
from aura.events import EventBus, GoalOutcomeRecorded
from aura.memory.episodic import EpisodicMemoryConsolidator
from aura.memory.store import SQLiteMemoryStore


def test_1_successful_execution_completes_goal(tmp_path):
    """Test 1: Successful plan execution sets PersistentGoal status to COMPLETED."""
    db_file = str(tmp_path / "test_stage5_1.db")
    store = GoalStore(db_path=db_file)
    mgr = GoalManager(store=store)

    goal = mgr.create_goal("Clean workbench", priority=GoalPriority.HIGH)
    assert goal.status == GoalStatus.PENDING

    plan = AgentPlan(
        goal=AgentGoal(description=goal.description, goal_id=goal.goal_id),
        tasks=[
            AgentTask(description="Clear tools", status=TaskStatus.SUCCESS),
            AgentTask(description="Wipe surface", status=TaskStatus.SUCCESS),
        ],
    )
    result = AgentExecutionResult(plan_id=plan.plan_id, completed=True)

    updated = mgr.record_execution_outcome(goal_id=goal.goal_id, plan=plan, result=result)

    assert updated is not None
    assert updated.status == GoalStatus.COMPLETED
    assert updated.progress.completion_percentage == 100.0


def test_2_partial_execution_updates_progress(tmp_path):
    """Test 2: Partial task execution updates completion percentage and leaves status ACTIVE."""
    db_file = str(tmp_path / "test_stage5_2.db")
    store = GoalStore(db_path=db_file)
    mgr = GoalManager(store=store)

    goal = mgr.create_goal("Multi-step task", priority=GoalPriority.MEDIUM)

    plan = AgentPlan(
        goal=AgentGoal(description=goal.description, goal_id=goal.goal_id),
        tasks=[
            AgentTask(description="Step 1", status=TaskStatus.SUCCESS),
            AgentTask(description="Step 2", status=TaskStatus.PENDING),
        ],
    )

    updated = mgr.record_execution_outcome(goal_id=goal.goal_id, plan=plan)

    assert updated is not None
    assert updated.status == GoalStatus.ACTIVE
    assert updated.progress.completion_percentage == 50.0


def test_3_failed_execution_sets_status_failed(tmp_path):
    """Test 3: Unrecoverable plan failure sets PersistentGoal status to FAILED."""
    db_file = str(tmp_path / "test_stage5_3.db")
    store = GoalStore(db_path=db_file)
    mgr = GoalManager(store=store)

    goal = mgr.create_goal("Failing task", priority=GoalPriority.HIGH)

    plan = AgentPlan(
        goal=AgentGoal(description=goal.description, goal_id=goal.goal_id),
        tasks=[AgentTask(description="Bad step", status=TaskStatus.FAILED, error="Syntax error")],
    )
    result = AgentExecutionResult(plan_id=plan.plan_id, failed=True)

    updated = mgr.record_execution_outcome(goal_id=goal.goal_id, plan=plan, result=result)

    assert updated is not None
    assert updated.status == GoalStatus.FAILED


def test_4_waiting_confirmation_blocks_goal(tmp_path):
    """Test 4: Plan waiting confirmation sets PersistentGoal status to BLOCKED."""
    db_file = str(tmp_path / "test_stage5_4.db")
    store = GoalStore(db_path=db_file)
    mgr = GoalManager(store=store)

    goal = mgr.create_goal("Sensitive operation", priority=GoalPriority.HIGH)

    plan = AgentPlan(
        goal=AgentGoal(description=goal.description, goal_id=goal.goal_id),
        tasks=[AgentTask(description="Destructive action", status=TaskStatus.WAITING_CONFIRMATION)],
    )
    result = AgentExecutionResult(plan_id=plan.plan_id, waiting_confirmation=True)

    updated = mgr.record_execution_outcome(goal_id=goal.goal_id, plan=plan, result=result)

    assert updated is not None
    assert updated.status == GoalStatus.BLOCKED


def test_5_cancelled_goal_not_selected(tmp_path):
    """Test 5: Logically cancelled goals are not selected by GoalSelector."""
    db_file = str(tmp_path / "test_stage5_5.db")
    store = GoalStore(db_path=db_file)
    mgr = GoalManager(store=store)

    goal = mgr.create_goal("Obsolete goal", priority=GoalPriority.CRITICAL)
    mgr.cancel_goal(goal.goal_id)

    prioritizer = GoalPrioritizer()
    prioritized = prioritizer.prioritize(mgr.list_goals())

    selector = GoalSelector()
    selected = selector.select_goal(prioritized)

    assert selected is None


def test_6_completed_goal_not_reselected(tmp_path):
    """Test 6: COMPLETED goals are excluded from subsequent goal selection."""
    db_file = str(tmp_path / "test_stage5_6.db")
    store = GoalStore(db_path=db_file)
    mgr = GoalManager(store=store)

    goal = mgr.create_goal("Finished task", priority=GoalPriority.HIGH)
    mgr.set_status(goal.goal_id, GoalStatus.COMPLETED)

    prioritizer = GoalPrioritizer()
    prioritized = prioritizer.prioritize(mgr.list_goals())

    selector = GoalSelector()
    selected = selector.select_goal(prioritized)

    assert selected is None


def test_7_failed_goal_replanning_behavior(tmp_path):
    """Test 7: FAILED goals remain unselected until explicitly reset or replanned."""
    db_file = str(tmp_path / "test_stage5_7.db")
    store = GoalStore(db_path=db_file)
    mgr = GoalManager(store=store)

    goal = mgr.create_goal("Failed attempt", priority=GoalPriority.HIGH)
    mgr.set_status(goal.goal_id, GoalStatus.FAILED)

    selector = GoalSelector()
    prioritized = GoalPrioritizer().prioritize(mgr.list_goals())
    assert selector.select_goal(prioritized) is None

    # Resetting status to PENDING allows re-selection
    mgr.set_status(goal.goal_id, GoalStatus.PENDING)
    prioritized_reset = GoalPrioritizer().prioritize(mgr.list_goals())
    selected = selector.select_goal(prioritized_reset)
    assert selected is not None
    assert selected.goal.goal_id == goal.goal_id


def test_8_progress_never_exceeds_100(tmp_path):
    """Test 8: Explicit progress values above 100% are clamped to 100%."""
    db_file = str(tmp_path / "test_stage5_8.db")
    store = GoalStore(db_path=db_file)
    mgr = GoalManager(store=store)

    goal = mgr.create_goal("Overflow progress", priority=GoalPriority.LOW)
    updated = mgr.record_execution_outcome(goal_id=goal.goal_id, progress_percentage=150.0)

    assert updated is not None
    assert updated.progress.completion_percentage == 100.0
    assert updated.status == GoalStatus.COMPLETED


def test_9_progress_never_below_0(tmp_path):
    """Test 9: Explicit progress values below 0% are clamped to 0%."""
    db_file = str(tmp_path / "test_stage5_9.db")
    store = GoalStore(db_path=db_file)
    mgr = GoalManager(store=store)

    goal = mgr.create_goal("Underflow progress", priority=GoalPriority.LOW)
    updated = mgr.record_execution_outcome(goal_id=goal.goal_id, progress_percentage=-25.0)

    assert updated is not None
    assert updated.progress.completion_percentage == 0.0


def test_10_terminal_state_idempotency(tmp_path):
    """Test 10: Goals in COMPLETED state ignore outcome recording updates idempotently."""
    db_file = str(tmp_path / "test_stage5_10.db")
    store = GoalStore(db_path=db_file)
    mgr = GoalManager(store=store)

    goal = mgr.create_goal("Already completed", priority=GoalPriority.HIGH)
    mgr.record_execution_outcome(goal_id=goal.goal_id, progress_percentage=100.0)

    # Attempting to record partial outcome on completed goal is a no-op
    updated = mgr.record_execution_outcome(goal_id=goal.goal_id, progress_percentage=30.0)
    assert updated is not None
    assert updated.status == GoalStatus.COMPLETED
    assert updated.progress.completion_percentage == 100.0


def test_11_goal_outcome_recorded_event_emitted(tmp_path):
    """Test 11: GoalManager emits GoalOutcomeRecorded event when recording outcome."""
    db_file = str(tmp_path / "test_stage5_11.db")
    store = GoalStore(db_path=db_file)
    bus = EventBus()
    mgr = GoalManager(store=store, event_bus=bus)

    events = []
    bus.subscribe(GoalOutcomeRecorded, lambda e: events.append(e))

    goal = mgr.create_goal("Event goal", priority=GoalPriority.MEDIUM)
    mgr.record_execution_outcome(goal_id=goal.goal_id, progress_percentage=100.0)

    assert len(events) == 1
    assert events[0].goal_id == goal.goal_id
    assert events[0].status == GoalStatus.COMPLETED.value


def test_12_episodic_memory_receives_plan_completed(tmp_path):
    """Test 12: AgentPlanCompleted event triggers episodic consolidation."""
    db_file = str(tmp_path / "test_stage5_12.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    bus = EventBus()

    consolidator = EpisodicMemoryConsolidator(store=sql_store, event_bus=bus)

    planner = AgentPlanner(event_bus=bus, deliberator=DeliberationEngine())
    executor = AgentExecutor(event_bus=bus)

    plan = planner.create_plan("Read sensor logs")
    executor.execute_plan(plan)

    episodes = consolidator.episodic_memory.search_episodes("sensor logs")
    assert len(episodes) > 0


def test_13_strategy_associated_with_outcome(tmp_path):
    """Test 13: Strategy ID and name are preserved in GoalOutcomeRecorded event."""
    db_file = str(tmp_path / "test_stage5_13.db")
    store = GoalStore(db_path=db_file)
    bus = EventBus()
    mgr = GoalManager(store=store, event_bus=bus)

    events = []
    bus.subscribe(GoalOutcomeRecorded, lambda e: events.append(e))

    goal = mgr.create_goal("Strategic task", priority=GoalPriority.HIGH)
    plan = AgentPlan(
        goal=AgentGoal(description=goal.description, goal_id=goal.goal_id),
        strategy_id="strat_001",
        strategy_name="OptimalStrategy",
        tasks=[AgentTask(description="Task 1", status=TaskStatus.SUCCESS)],
    )

    mgr.record_execution_outcome(goal_id=goal.goal_id, plan=plan)

    assert len(events) == 1
    assert events[0].strategy_id == "strat_001"


def test_14_reprioritization_after_goal_modification(tmp_path):
    """Test 14: Updating a goal's priority reorders GoalPrioritizer rankings."""
    db_file = str(tmp_path / "test_stage5_14.db")
    store = GoalStore(db_path=db_file)
    mgr = GoalManager(store=store)

    g1 = mgr.create_goal("Low task", priority=GoalPriority.LOW)
    g2 = mgr.create_goal("Medium task", priority=GoalPriority.MEDIUM)

    prioritizer = GoalPrioritizer()
    p1 = prioritizer.prioritize(mgr.list_goals())
    assert p1[0].goal.goal_id == g2.goal_id

    # Upgrade g1 to CRITICAL
    mgr.update_goal(g1.goal_id, priority=GoalPriority.CRITICAL)

    p2 = prioritizer.prioritize(mgr.list_goals())
    assert p2[0].goal.goal_id == g1.goal_id


def test_15_select_next_goal_after_completion(tmp_path):
    """Test 15: Completing top goal advances GoalSelector to next eligible goal."""
    db_file = str(tmp_path / "test_stage5_15.db")
    store = GoalStore(db_path=db_file)
    mgr = GoalManager(store=store)

    g1 = mgr.create_goal("Top priority", priority=GoalPriority.HIGH)
    g2 = mgr.create_goal("Second priority", priority=GoalPriority.MEDIUM)

    prioritizer = GoalPrioritizer()
    selector = GoalSelector()

    # Initial selection picks g1
    s1 = selector.select_goal(prioritizer.prioritize(mgr.list_goals()))
    assert s1 is not None and s1.goal.goal_id == g1.goal_id

    # Complete g1
    mgr.set_status(g1.goal_id, GoalStatus.COMPLETED)

    # Next selection picks g2
    s2 = selector.select_goal(prioritizer.prioritize(mgr.list_goals()))
    assert s2 is not None and s2.goal.goal_id == g2.goal_id


def test_16_absence_of_eligible_goals_returns_none(tmp_path):
    """Test 16: execute_goal_cycle returns None tuple when no eligible goals exist."""
    db_file = str(tmp_path / "test_stage5_16.db")
    store = GoalStore(db_path=db_file)
    mgr = GoalManager(store=store)

    planner = AgentPlanner(deliberator=DeliberationEngine())
    executor = AgentExecutor()

    res = planner.execute_goal_cycle(goal_manager=mgr, executor=executor)
    assert res == (None, None, None, None)


def test_17_duplicate_execution_outcome_idempotent(tmp_path):
    """Test 17: Recording duplicate execution outcomes on same goal is idempotent."""
    db_file = str(tmp_path / "test_stage5_17.db")
    store = GoalStore(db_path=db_file)
    mgr = GoalManager(store=store)

    goal = mgr.create_goal("Idempotent run", priority=GoalPriority.MEDIUM)
    plan = AgentPlan(
        goal=AgentGoal(description=goal.description, goal_id=goal.goal_id),
        tasks=[AgentTask(description="T1", status=TaskStatus.SUCCESS)],
    )

    u1 = mgr.record_execution_outcome(goal_id=goal.goal_id, plan=plan)
    u2 = mgr.record_execution_outcome(goal_id=goal.goal_id, plan=plan)

    assert u1 is not None and u2 is not None
    assert u1.status == u2.status == GoalStatus.COMPLETED
    assert u1.progress.completion_percentage == u2.progress.completion_percentage == 100.0


def test_18_executor_does_not_access_sqlite_directly():
    """Test 18: AgentExecutor does not instantiate or query SQLite database directly."""
    executor = AgentExecutor()
    assert not hasattr(executor, "store")
    assert not hasattr(executor, "db_path")


def test_19_e2e_cycle_goal_completion_and_advance(tmp_path):
    """Test 19: Full E2E cycle: Goal A completed -> Goal B selected."""
    db_file = str(tmp_path / "test_stage5_e2e_1.db")
    store = GoalStore(db_path=db_file)
    mgr = GoalManager(store=store)

    g_a = mgr.create_goal("Goal A - High", priority=GoalPriority.HIGH)
    g_b = mgr.create_goal("Goal B - Low", priority=GoalPriority.LOW)

    planner = AgentPlanner(deliberator=DeliberationEngine())
    executor = AgentExecutor()

    # Cycle 1: Selects and completes Goal A
    selected1, _, _plan1, _result1 = planner.execute_goal_cycle(goal_manager=mgr, executor=executor)

    assert selected1 is not None and selected1.goal.goal_id == g_a.goal_id
    assert mgr.get_goal(g_a.goal_id).status == GoalStatus.COMPLETED

    # Cycle 2: Automatically advances to Goal B
    selected2, _, _plan2, _result2 = planner.execute_goal_cycle(goal_manager=mgr, executor=executor)

    assert selected2 is not None and selected2.goal.goal_id == g_b.goal_id


def test_20_e2e_cycle_partial_failure_and_reprioritization(tmp_path):
    """Test 20: Full E2E cycle: Goal A fails -> Goal A set FAILED -> Goal B selected next."""
    db_file = str(tmp_path / "test_stage5_e2e_2.db")
    store = GoalStore(db_path=db_file)
    mgr = GoalManager(store=store)

    g_a = mgr.create_goal("Failing Goal A", priority=GoalPriority.HIGH)
    g_b = mgr.create_goal("Backlog Goal B", priority=GoalPriority.LOW)

    # Mock an executor that fails plans
    class FailingExecutor(AgentExecutor):
        def execute_plan(self, plan, registry=None):
            for t in plan.tasks:
                t.status = TaskStatus.FAILED
                t.error = "Simulated hardware fault"
            return AgentExecutionResult(plan_id=plan.plan_id, failed=True)

    planner = AgentPlanner(deliberator=DeliberationEngine())
    executor = FailingExecutor()

    # Cycle 1: Goal A fails
    selected1, _, _plan1, _result1 = planner.execute_goal_cycle(goal_manager=mgr, executor=executor)
    assert selected1 is not None and selected1.goal.goal_id == g_a.goal_id
    assert mgr.get_goal(g_a.goal_id).status == GoalStatus.FAILED

    # Cycle 2: Goal A (FAILED) is skipped, Goal B is selected next
    selected2, _, _plan2, _result2 = planner.execute_goal_cycle(goal_manager=mgr, executor=executor)
    assert selected2 is not None and selected2.goal.goal_id == g_b.goal_id
