from aura.cognition.context import CognitiveContextBuilder
from aura.cognition.goals import (
    GoalManager,
    GoalPrioritizer,
    GoalPriority,
    GoalStatus,
    GoalStore,
    PersistentGoal,
)
from aura.container import DependencyContainer


def test_1_basic_prioritizer_construction():
    """Test 1: GoalPrioritizer initializes cleanly."""
    prioritizer = GoalPrioritizer()
    assert prioritizer is not None


def test_2_single_goal_prioritization():
    """Test 2: Prioritizing a single goal produces 1 PrioritizedGoal with rank 1."""
    goal = PersistentGoal(description="Single goal test")
    prioritizer = GoalPrioritizer()
    prioritized = prioritizer.prioritize([goal])

    assert len(prioritized) == 1
    assert prioritized[0].rank == 1
    assert prioritized[0].goal.goal_id == goal.goal_id
    assert isinstance(prioritized[0].explanation, str)


def test_3_multiple_goals_prioritization():
    """Test 3: Prioritizing multiple goals ranks them all with 1-based indexing."""
    g1 = PersistentGoal(description="G1", priority=GoalPriority.LOW)
    g2 = PersistentGoal(description="G2", priority=GoalPriority.HIGH)
    prioritizer = GoalPrioritizer()
    prioritized = prioritizer.prioritize([g1, g2])

    assert len(prioritized) == 2
    assert [p.rank for p in prioritized] == [1, 2]


def test_4_higher_explicit_priority_wins():
    """Test 4: Higher explicit priority dominates ranking."""
    low_goal = PersistentGoal(description="Low goal", priority=GoalPriority.LOW)
    crit_goal = PersistentGoal(description="Crit goal", priority=GoalPriority.CRITICAL)

    prioritizer = GoalPrioritizer()
    prioritized = prioritizer.prioritize([low_goal, crit_goal])

    assert prioritized[0].goal.goal_id == crit_goal.goal_id
    assert prioritized[1].goal.goal_id == low_goal.goal_id


def test_5_deterministic_tie_breaking():
    """Test 5: Identical score goals tie-break deterministically by created_at then goal_id."""
    g1 = PersistentGoal(description="G1", created_at="2026-01-01T10:00:00Z", goal_id="pgoal_aaa")
    g2 = PersistentGoal(description="G2", created_at="2026-01-01T10:00:00Z", goal_id="pgoal_bbb")

    prioritizer = GoalPrioritizer()
    res1 = prioritizer.prioritize([g2, g1])
    res2 = prioritizer.prioritize([g1, g2])

    assert [p.goal.goal_id for p in res1] == ["pgoal_aaa", "pgoal_bbb"]
    assert [p.goal.goal_id for p in res2] == ["pgoal_aaa", "pgoal_bbb"]


def test_6_terminal_states_penalty():
    """Test 6: Terminal states (COMPLETED, FAILED, CANCELLED) rank lower than PENDING or ACTIVE."""
    active_low = PersistentGoal(
        description="Active low", priority=GoalPriority.LOW, status=GoalStatus.ACTIVE
    )
    completed_crit = PersistentGoal(
        description="Completed crit", priority=GoalPriority.CRITICAL, status=GoalStatus.COMPLETED
    )

    prioritizer = GoalPrioritizer()
    prioritized = prioritizer.prioritize([completed_crit, active_low])

    assert prioritized[0].goal.goal_id == active_low.goal_id
    assert prioritized[1].goal.goal_id == completed_crit.goal_id


def test_7_progress_influence():
    """Test 7: Lower completion percentage provides a slight priority bonus for active goals."""
    g_0_percent = PersistentGoal(description="0% done", priority=GoalPriority.HIGH)
    g_90_percent = PersistentGoal(description="90% done", priority=GoalPriority.HIGH)
    g_90_percent.progress.completion_percentage = 90.0

    prioritizer = GoalPrioritizer()
    prioritized = prioritizer.prioritize([g_90_percent, g_0_percent])

    assert prioritized[0].goal.goal_id == g_0_percent.goal_id


def test_8_deterministic_explanation():
    """Test 8: Explanation string is human-readable and deterministic."""
    goal = PersistentGoal(
        description="Explain test", priority=GoalPriority.HIGH, status=GoalStatus.ACTIVE
    )
    prioritizer = GoalPrioritizer()
    prioritized = prioritizer.prioritize([goal])

    exp = prioritized[0].explanation
    assert "Priority HIGH" in exp
    assert "Status ACTIVE" in exp


def test_9_rank_assignment():
    """Test 9: Rank numbers are 1-indexed strictly sequential."""
    goals = [PersistentGoal(description=f"G{i}") for i in range(5)]
    prioritizer = GoalPrioritizer()
    prioritized = prioritizer.prioritize(goals)

    assert [p.rank for p in prioritized] == [1, 2, 3, 4, 5]


def test_10_comparable_scores():
    """Test 10: Scores are comparable floats."""
    crit = PersistentGoal(description="Crit", priority=GoalPriority.CRITICAL)
    low = PersistentGoal(description="Low", priority=GoalPriority.LOW)

    prioritizer = GoalPrioritizer()
    res = prioritizer.prioritize([crit, low])

    assert res[0].score > res[1].score


def test_11_empty_input_returns_empty():
    """Test 11: Empty goal list returns empty list."""
    prioritizer = GoalPrioritizer()
    assert prioritizer.prioritize([]) == []


def test_12_goals_unmutated():
    """Test 12: Input PersistentGoal instances are not mutated by prioritization."""
    goal = PersistentGoal(description="Unmutated test")
    orig_status = goal.status
    orig_priority = goal.priority

    prioritizer = GoalPrioritizer()
    prioritizer.prioritize([goal])

    assert goal.status == orig_status
    assert goal.priority == orig_priority


def test_13_deterministic_repeatability():
    """Test 13: Same input produces identical outputs repeatedly."""
    g1 = PersistentGoal(description="Alpha", priority=GoalPriority.HIGH)
    g2 = PersistentGoal(description="Beta", priority=GoalPriority.MEDIUM)

    prioritizer = GoalPrioritizer()
    run1 = prioritizer.prioritize([g1, g2])
    run2 = prioritizer.prioritize([g1, g2])

    assert [(p.goal.goal_id, p.score, p.rank) for p in run1] == [
        (p.goal.goal_id, p.score, p.rank) for p in run2
    ]


def test_14_different_ids():
    """Test 14: Goals with distinct IDs rank properly without collision."""
    g1 = PersistentGoal(description="A", goal_id="id_1")
    g2 = PersistentGoal(description="B", goal_id="id_2")

    prioritizer = GoalPrioritizer()
    res = prioritizer.prioritize([g1, g2])
    assert len(res) == 2


def test_15_equal_priorities():
    """Test 15: Equal explicit priority goals are differentiated by status and progress."""
    g_pending = PersistentGoal(
        description="Pending", priority=GoalPriority.MEDIUM, status=GoalStatus.PENDING
    )
    g_active = PersistentGoal(
        description="Active", priority=GoalPriority.MEDIUM, status=GoalStatus.ACTIVE
    )

    prioritizer = GoalPrioritizer()
    res = prioritizer.prioritize([g_pending, g_active])

    assert res[0].goal.goal_id == g_active.goal_id


def test_16_multi_factor_scoring_combination():
    """Test 16: Multi-factor scoring correctly combines priority, status, and progress weights."""
    g_critical_paused = PersistentGoal(
        description="Crit paused", priority=GoalPriority.CRITICAL, status=GoalStatus.PAUSED
    )
    g_high_active = PersistentGoal(
        description="High active", priority=GoalPriority.HIGH, status=GoalStatus.ACTIVE
    )

    prioritizer = GoalPrioritizer()
    res = prioritizer.prioritize([g_critical_paused, g_high_active])

    # CRITICAL (40) + PAUSED (0) + 10 = 50.0
    # HIGH (30) + ACTIVE (15) + 10 = 55.0 -> HIGH ACTIVE wins!
    assert res[0].goal.goal_id == g_high_active.goal_id


def test_17_optional_fields():
    """Test 17: Default persistent goals prioritize without error."""
    goal = PersistentGoal(description="Defaults goal")
    prioritizer = GoalPrioritizer()
    res = prioritizer.prioritize([goal])
    assert len(res) == 1


def test_18_edge_case_100_percent_completed_active():
    """Test 18: Active goal with 100% completion has lower bonus than 0% active goal."""
    g_100 = PersistentGoal(
        description="100% active", priority=GoalPriority.MEDIUM, status=GoalStatus.ACTIVE
    )
    g_100.progress.completion_percentage = 100.0

    g_0 = PersistentGoal(
        description="0% active", priority=GoalPriority.MEDIUM, status=GoalStatus.ACTIVE
    )
    g_0.progress.completion_percentage = 0.0

    prioritizer = GoalPrioritizer()
    res = prioritizer.prioritize([g_100, g_0])

    assert res[0].goal.goal_id == g_0.goal_id


def test_19_cognitive_context_integration(tmp_path):
    """Test 19: CognitiveContextBuilder injects prioritized goals into CognitiveContext."""
    db_file = str(tmp_path / "test_stage3_context.db")
    store = GoalStore(db_path=db_file)
    mgr = GoalManager(store=store)

    mgr.create_goal("Organizar escritorio de trabajo", priority=GoalPriority.HIGH)
    mgr.create_goal("Comprar suministros de oficina", priority=GoalPriority.LOW)

    container = DependencyContainer()
    container.register(GoalManager, instance=mgr)

    builder = CognitiveContextBuilder(container=container)
    ctx = builder.build(input_text="¿Qué debo hacer hoy?")

    assert len(ctx.prioritized_goals) == 2
    prompt = ctx.to_system_prompt()
    assert "[OBJETIVOS PERSISTENTES PRIORIZADOS]:" in prompt
    assert "Organizar escritorio de trabajo" in prompt
    assert "#1 Score" in prompt
