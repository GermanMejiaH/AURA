from __future__ import annotations

import json
import re
from unittest.mock import MagicMock

import pytest

from aura.autonomy.agent_models import AgentGoal, AgentPlan, TaskStatus
from aura.autonomy.executor import AgentExecutor
from aura.autonomy.history import AgentExecutionHistoryStore
from aura.autonomy.planner import AgentPlanner
from aura.cognition.deliberation import (
    DeliberationEngine,
    GoalModel,
    OutcomeSimulator,
    RiskLevel,
    StrategyCandidate,
    StrategySelection,
    StrategySelector,
)
from aura.events import (
    EventBus,
    StrategyDeliberated,
    StrategySelected,
)
from aura.memory.episodic import Episode, EpisodicMemory, EpisodicMemoryConsolidator
from aura.memory.retrieval import MemoryRetriever
from aura.memory.store import SQLiteMemoryStore


@pytest.fixture
def memory_setup(tmp_path):
    db_file = str(tmp_path / "test_stage4.db")
    store = SQLiteMemoryStore(db_path=db_file)
    bus = EventBus()
    history = AgentExecutionHistoryStore(store=store, event_bus=bus)
    mem = EpisodicMemory(store=store)
    retriever = MemoryRetriever(store=store)
    consolidator = EpisodicMemoryConsolidator(episodic_memory=mem, history_store=history)
    bus.subscribe("*", consolidator.handle_event)
    return store, mem, retriever, consolidator, bus


def test_1_goal_model_enters_full_pipeline(memory_setup):
    """Test 1: GoalModel enters the full E2E pipeline producing selection and plan."""
    _, _, retriever, _, bus = memory_setup
    events_captured = []
    bus.subscribe("*", lambda e: events_captured.append(e))

    planner = AgentPlanner(
        event_bus=bus,
        deliberator=DeliberationEngine(),
        simulator=OutcomeSimulator(retriever),
        selector=StrategySelector(),
    )

    goal = GoalModel(description="Optimize database indexes", priority=2.0)
    selection, plan = planner.deliberate_and_plan(goal)

    assert isinstance(selection, StrategySelection)
    assert isinstance(plan, AgentPlan)
    assert plan.strategy_id == selection.chosen_strategy.strategy_id
    assert any(isinstance(e, StrategyDeliberated) for e in events_captured)
    assert any(isinstance(e, StrategySelected) for e in events_captured)


def test_2_deliberation_engine_generates_candidates():
    """Test 2: DeliberationEngine generates up to 3 StrategyCandidates."""
    engine = DeliberationEngine()
    goal = GoalModel(description="Build pipeline")
    candidates = engine.deliberate(goal)

    assert 1 <= len(candidates) <= 3
    assert all(isinstance(c, StrategyCandidate) for c in candidates)


def test_3_outcome_simulator_simulates_all_candidates(memory_setup):
    """Test 3: OutcomeSimulator simulates consequences for each candidate strategy."""
    _, _, retriever, _, _ = memory_setup
    engine = DeliberationEngine()
    simulator = OutcomeSimulator(retriever)
    goal = GoalModel(description="Process batch data")

    candidates = engine.deliberate(goal)
    simulations = [simulator.simulate(c, goal) for c in candidates]

    assert len(simulations) == len(candidates)
    assert all(
        s.strategy_id == c.strategy_id for s, c in zip(simulations, candidates, strict=False)
    )


def test_4_strategy_selector_selects_single_strategy(memory_setup):
    """Test 4: StrategySelector chooses exactly 1 optimal strategy."""
    _, _, retriever, _, _ = memory_setup
    engine = DeliberationEngine()
    simulator = OutcomeSimulator(retriever)
    selector = StrategySelector()
    goal = GoalModel(description="Clean logs")

    candidates = engine.deliberate(goal)
    simulations = [simulator.simulate(c, goal) for c in candidates]
    selection = selector.select(goal, candidates, simulations)

    assert isinstance(selection, StrategySelection)
    assert selection.chosen_strategy in candidates


def test_5_only_selected_strategy_reaches_planner(memory_setup):
    """Test 5: Only the strategy chosen by StrategySelector is converted into the AgentPlan."""
    _, _, retriever, _, _ = memory_setup
    planner = AgentPlanner(
        deliberator=DeliberationEngine(),
        simulator=OutcomeSimulator(retriever),
        selector=StrategySelector(),
    )
    goal = GoalModel(description="Execute migration")
    selection, plan = planner.deliberate_and_plan(goal)

    assert plan.strategy_id == selection.chosen_strategy.strategy_id
    assert plan.strategy_name == selection.chosen_strategy.name


def test_6_rejected_strategies_never_execute(memory_setup):
    """Test 6: Rejected candidate strategies are recorded in rejection_reasons and not planned."""
    _, _, retriever, _, _ = memory_setup
    planner = AgentPlanner(
        deliberator=DeliberationEngine(),
        simulator=OutcomeSimulator(retriever),
        selector=StrategySelector(),
    )
    goal = GoalModel(
        description="Inspect files safely",
        constraints=["no_cmd execution"],
    )
    selection, plan = planner.deliberate_and_plan(goal)

    for rej_id in selection.rejection_reasons:
        assert rej_id != plan.strategy_id


def test_7_selected_strategy_generates_valid_agent_tasks(memory_setup):
    """Test 7: AgentPlan tasks match the chosen strategy steps_outline."""
    _, _, retriever, _, _ = memory_setup
    planner = AgentPlanner(
        deliberator=DeliberationEngine(),
        simulator=OutcomeSimulator(retriever),
        selector=StrategySelector(),
    )
    goal = GoalModel(description="Transform data file")
    selection, plan = planner.deliberate_and_plan(goal)

    assert len(plan.tasks) == len(selection.chosen_strategy.steps_outline)
    for t, step in zip(plan.tasks, selection.chosen_strategy.steps_outline, strict=False):
        assert t.description == step
        assert t.status == TaskStatus.PENDING


def test_8_agent_executor_executes_selected_plan(memory_setup):
    """Test 8: AgentExecutor runs tasks in the selected plan to completion."""
    _, _, retriever, _, _ = memory_setup
    planner = AgentPlanner(
        deliberator=DeliberationEngine(),
        simulator=OutcomeSimulator(retriever),
        selector=StrategySelector(),
    )
    goal = GoalModel(description="Basic run")
    _, plan = planner.deliberate_and_plan(goal)

    executor = AgentExecutor()
    res = executor.execute_plan(plan)

    assert res.completed is True
    assert res.failed is False
    assert res.steps_executed == len(plan.tasks)


def test_9_verify_continues_working(memory_setup):
    """Test 9: ActionVerifier verifies execution steps during AgentExecutor run."""
    _, _, retriever, _, _ = memory_setup
    planner = AgentPlanner(
        deliberator=DeliberationEngine(),
        simulator=OutcomeSimulator(retriever),
        selector=StrategySelector(),
    )
    goal = GoalModel(description="Verified run")
    _, plan = planner.deliberate_and_plan(goal)

    mock_verifier = MagicMock()
    mock_verifier.verify.return_value.status.value = "SUCCESS"
    executor = AgentExecutor(verifier=mock_verifier)

    res = executor.execute_plan(plan)
    assert res.completed is True
    assert mock_verifier.verify.call_count >= 1


def test_10_reflect_continues_working(memory_setup):
    """Test 10: CognitiveReflector generates ReflectionSummary for verification outcomes."""
    _, _, retriever, _, _ = memory_setup
    planner = AgentPlanner(
        deliberator=DeliberationEngine(),
        simulator=OutcomeSimulator(retriever),
        selector=StrategySelector(),
    )
    goal = GoalModel(description="Reflected run")
    _, plan = planner.deliberate_and_plan(goal)

    mock_reflector = MagicMock()
    executor = AgentExecutor(reflector=mock_reflector)

    res = executor.execute_plan(plan)
    assert res.completed is True
    assert mock_reflector.reflect.call_count >= 1


def test_11_learn_continues_working(memory_setup):
    """Test 11: EpisodicMemoryConsolidator records the completed plan as an episode."""
    store, _mem, retriever, _consolidator, bus = memory_setup

    planner = AgentPlanner(
        event_bus=bus,
        deliberator=DeliberationEngine(),
        simulator=OutcomeSimulator(retriever),
        selector=StrategySelector(),
    )
    goal = GoalModel(description="Learning execution run")
    _, plan = planner.deliberate_and_plan(goal)

    executor = AgentExecutor(event_bus=bus)
    executor.execute_plan(plan)

    episodes = store.get_episodes()
    assert len(episodes) >= 1
    assert any("Learning execution run" in ep.summary for ep in episodes)


def test_12_strategy_recorded_in_episodic_memory(memory_setup):
    """Test 12: Strategy details (strategy_id, strategy_name) are persisted in Episode details."""
    store, _mem, retriever, _consolidator, bus = memory_setup

    planner = AgentPlanner(
        event_bus=bus,
        deliberator=DeliberationEngine(),
        simulator=OutcomeSimulator(retriever),
        selector=StrategySelector(),
    )
    goal = GoalModel(description="Persist strategy run")
    selection, plan = planner.deliberate_and_plan(goal)

    executor = AgentExecutor(event_bus=bus)
    executor.execute_plan(plan)

    episodes = store.get_episodes()
    assert len(episodes) >= 1
    latest_details = json.loads(episodes[0].details)
    assert latest_details.get("strategy_id") == selection.chosen_strategy.strategy_id
    assert latest_details.get("strategy_name") == selection.chosen_strategy.name


def test_13_legacy_episodes_continue_working(memory_setup):
    """Test 13: Memory retriever and simulator process legacy episodes without strategy fields."""
    store, _mem, retriever, _consolidator, _bus = memory_setup
    legacy_ep = Episode(
        id="legacy_001",
        summary="Legacy run",
        details=json.dumps({"outcome": "SUCCESS", "tools_used": ["old_tool"]}),
    )
    store.save_episode(legacy_ep)

    simulator = OutcomeSimulator(retriever)
    goal = GoalModel(description="Legacy memory query")
    candidate = StrategyCandidate(strategy_id="s1", name="S1", description="")

    outcome = simulator.simulate(candidate, goal)
    assert outcome.estimated_success_rate == 0.80


def test_14_legacy_agent_goal_continues_working(memory_setup):
    """Test 14: AgentPlanner handles plain string or AgentGoal objects without error."""
    _, _, retriever, _, _ = memory_setup
    planner = AgentPlanner(
        deliberator=DeliberationEngine(),
        simulator=OutcomeSimulator(retriever),
        selector=StrategySelector(),
    )

    plan_str = planner.create_plan("Plain string goal")
    assert isinstance(plan_str, AgentPlan)

    plain_goal = AgentGoal(description="Plain AgentGoal")
    plan_obj = planner.create_plan(plain_goal)
    assert isinstance(plan_obj, AgentPlan)


def test_15_pipeline_is_deterministic(memory_setup):
    """Test 15: Full E2E pipeline produces identical selections and plans for identical inputs."""
    _, _, retriever, _, _ = memory_setup
    planner = AgentPlanner(
        deliberator=DeliberationEngine(),
        simulator=OutcomeSimulator(retriever),
        selector=StrategySelector(),
    )
    goal = GoalModel(description="Deterministic run", goal_id="g_det_e2e")

    sel1, plan1 = planner.deliberate_and_plan(goal)
    sel2, plan2 = planner.deliberate_and_plan(goal)

    assert sel1.chosen_strategy.strategy_id == sel2.chosen_strategy.strategy_id
    assert [t.description for t in plan1.tasks] == [t.description for t in plan2.tasks]


def test_16_no_unexpected_side_effects():
    """Test 16: Deliberation and planning leave input GoalModel unmutated."""
    goal = GoalModel(description="Side effect test", priority=3.0)
    planner = AgentPlanner(
        deliberator=DeliberationEngine(),
        simulator=OutcomeSimulator(MagicMock(spec=MemoryRetriever)),
        selector=StrategySelector(),
    )

    orig_status = goal.status
    orig_priority = goal.priority

    _ = planner.deliberate_and_plan(goal)

    assert goal.status == orig_status
    assert goal.priority == orig_priority


def test_17_no_tools_executed_during_deliberation(memory_setup):
    """Test 17: Deliberation, simulation, and selection execute zero tools."""
    _, _, retriever, _, _ = memory_setup
    registry_mock = MagicMock()

    planner = AgentPlanner(
        registry=registry_mock,
        deliberator=DeliberationEngine(),
        simulator=OutcomeSimulator(retriever),
        selector=StrategySelector(),
    )
    goal = GoalModel(description="No execution test")
    planner.deliberate_and_plan(goal)

    assert registry_mock.execute.call_count == 0


def test_18_simulation_failures_handled_safely():
    """Test 18: Fallback handling when MemoryRetriever search throws an exception."""
    bad_retriever = MagicMock(spec=MemoryRetriever)
    bad_retriever.search.side_effect = RuntimeError("Store error")

    planner = AgentPlanner(
        deliberator=DeliberationEngine(),
        simulator=OutcomeSimulator(bad_retriever),
        selector=StrategySelector(),
    )
    goal = GoalModel(description="Resilience test")

    selection, plan = planner.deliberate_and_plan(goal)
    assert isinstance(selection, StrategySelection)
    assert isinstance(plan, AgentPlan)


def test_19_no_viable_strategy_handled_correctly(memory_setup):
    """Test 19: Raises ValueError when all generated candidate strategies violate constraints."""
    _, _, retriever, _, _ = memory_setup
    mock_registry = MagicMock()
    mock_meta = MagicMock()
    mock_meta.name = "cmd"
    mock_registry.list_metadata.return_value = [mock_meta]

    planner = AgentPlanner(
        registry=mock_registry,
        deliberator=DeliberationEngine(),
        simulator=OutcomeSimulator(retriever),
        selector=StrategySelector(),
    )
    goal = GoalModel(
        description="Impossible constraints",
        constraints=["no_cmd execution"],
        risk_tolerance=RiskLevel.LOW,
    )

    with pytest.raises(ValueError, match=re.escape("No viable strategy found for goal")):
        planner.deliberate_and_plan(goal)


def test_20_no_infinite_deliberation_loops(memory_setup):
    """Test 20: Pipeline executes single pass deliberation without infinite recursion loops."""
    _, _, retriever, _, _ = memory_setup
    planner = AgentPlanner(
        deliberator=DeliberationEngine(),
        simulator=OutcomeSimulator(retriever),
        selector=StrategySelector(),
    )
    goal = GoalModel(description="Single pass test")

    _selection, plan = planner.deliberate_and_plan(goal)
    assert plan.replan_count == 0
    assert len(plan.tasks) > 0
