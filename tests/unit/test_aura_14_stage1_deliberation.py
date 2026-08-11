from __future__ import annotations

import re

import pytest

from aura.autonomy.agent_models import AgentGoal, TaskStatus
from aura.cognition.deliberation import (
    DeliberationEngine,
    GoalModel,
    RiskLevel,
    SimulationOutcome,
    StrategyCandidate,
    StrategySelection,
)


def test_1_goal_model_construction():
    """Test 1: GoalModel constructs cleanly, extending AgentGoal attributes."""
    goal = GoalModel(
        description="Optimize database queries",
        priority=2.5,
        constraints=["Max memory 512MB"],
        success_criteria=["Latency under 50ms"],
        risk_tolerance=RiskLevel.LOW,
    )
    assert isinstance(goal, AgentGoal)
    assert goal.description == "Optimize database queries"
    assert goal.priority == 2.5
    assert goal.constraints == ["Max memory 512MB"]
    assert goal.success_criteria == ["Latency under 50ms"]
    assert goal.risk_tolerance == RiskLevel.LOW
    assert goal.status == TaskStatus.PENDING


def test_2_risk_level_enum_values():
    """Test 2: RiskLevel enum contains LOW, MEDIUM, HIGH, and CRITICAL levels."""
    levels = [r.value for r in RiskLevel]
    assert "LOW" in levels
    assert "MEDIUM" in levels
    assert "HIGH" in levels
    assert "CRITICAL" in levels
    assert len(levels) == 4


def test_3_strategy_candidate_construction():
    """Test 3: StrategyCandidate constructs with required and default parameters."""
    strat = StrategyCandidate(
        strategy_id="strat_001",
        name="Sequential API Calls",
        description="Calls endpoints in order",
        steps_outline=["Auth", "Fetch", "Parse"],
        required_tools=["http_client"],
        estimated_complexity=2.0,
    )
    assert strat.strategy_id == "strat_001"
    assert strat.name == "Sequential API Calls"
    assert strat.estimated_complexity == 2.0


def test_4_simulation_outcome_construction():
    """Test 4: SimulationOutcome constructs correctly with risk and success metrics."""
    sim = SimulationOutcome(
        strategy_id="strat_001",
        estimated_success_rate=0.85,
        risk_score=0.2,
        risk_level=RiskLevel.LOW,
        potential_bottlenecks=["Network delay"],
        matched_lessons=["Use backoff"],
        explanation="Low risk execution path",
    )
    assert sim.strategy_id == "strat_001"
    assert sim.estimated_success_rate == 0.85
    assert sim.risk_score == 0.2
    assert sim.risk_level == RiskLevel.LOW


def test_5_strategy_selection_construction():
    """Test 5: StrategySelection encapsulates chosen candidate and comparison metadata."""
    strat = StrategyCandidate(
        strategy_id="strat_001",
        name="Direct Strategy",
        description="Direct execution",
        estimated_complexity=1.0,
    )
    sim = SimulationOutcome(
        strategy_id="strat_001",
        estimated_success_rate=0.9,
        risk_score=0.1,
        risk_level=RiskLevel.LOW,
    )
    selection = StrategySelection(
        goal_id="goal_123",
        chosen_strategy=strat,
        chosen_simulation=sim,
        all_candidates=[strat],
        comparison_summary="Direct strategy selected as optimal",
        rejection_reasons={},
    )
    assert selection.goal_id == "goal_123"
    assert selection.chosen_strategy.strategy_id == "strat_001"


def test_6_invalid_priority_rejected():
    """Test 6: GoalModel rejects priority < 0.0 with ValueError."""
    with pytest.raises(ValueError, match=re.escape("priority must be >= 0.0")):
        GoalModel(description="Invalid priority", priority=-0.5)


def test_7_invalid_estimated_complexity_rejected():
    """Test 7: StrategyCandidate rejects estimated_complexity outside 1.0 - 5.0."""
    with pytest.raises(
        ValueError, match=re.escape("estimated_complexity must be between 1.0 and 5.0")
    ):
        StrategyCandidate(
            strategy_id="strat_inv",
            name="Too complex",
            description="Desc",
            estimated_complexity=6.0,
        )

    with pytest.raises(
        ValueError, match=re.escape("estimated_complexity must be between 1.0 and 5.0")
    ):
        StrategyCandidate(
            strategy_id="strat_inv2",
            name="Negative complexity",
            description="Desc",
            estimated_complexity=0.5,
        )


def test_8_invalid_estimated_success_rate_rejected():
    """Test 8: SimulationOutcome rejects estimated_success_rate outside 0.0 - 1.0."""
    with pytest.raises(
        ValueError, match=re.escape("estimated_success_rate must be between 0.0 and 1.0")
    ):
        SimulationOutcome(
            strategy_id="strat_inv",
            estimated_success_rate=1.5,
            risk_score=0.5,
            risk_level=RiskLevel.MEDIUM,
        )


def test_9_invalid_risk_score_rejected():
    """Test 9: SimulationOutcome rejects risk_score outside 0.0 - 1.0."""
    with pytest.raises(ValueError, match=re.escape("risk_score must be between 0.0 and 1.0")):
        SimulationOutcome(
            strategy_id="strat_inv",
            estimated_success_rate=0.8,
            risk_score=-0.1,
            risk_level=RiskLevel.LOW,
        )


def test_10_deliberation_engine_produces_candidates():
    """Test 10: DeliberationEngine generates a list of strategy candidates for a GoalModel."""
    engine = DeliberationEngine()
    goal = GoalModel(description="Calculo de nomina")
    candidates = engine.deliberate(goal)

    assert isinstance(candidates, list)
    assert len(candidates) > 0
    assert all(isinstance(c, StrategyCandidate) for c in candidates)


def test_11_deliberation_engine_max_3_candidates():
    """Test 11: DeliberationEngine never produces more than 3 candidates."""
    engine = DeliberationEngine()
    goal = GoalModel(description="Complex multi-system integration goal")
    tools = ["read_file", "write_file", "execute_cmd", "check_status", "http_request"]
    candidates = engine.deliberate(goal, available_tools=tools)

    assert len(candidates) <= 3


def test_12_deliberation_determinism():
    """Test 12: Identical inputs produce identical candidates and properties."""
    engine = DeliberationEngine()
    goal = GoalModel(description="Deterministic calculation", goal_id="goal_det_001")
    tools = ["calculator_tool", "logger_tool"]

    cands1 = engine.deliberate(goal, available_tools=tools)
    cands2 = engine.deliberate(goal, available_tools=tools)

    assert len(cands1) == len(cands2)
    for c1, c2 in zip(cands1, cands2, strict=False):
        assert c1.strategy_id == c2.strategy_id
        assert c1.name == c2.name
        assert c1.description == c2.description
        assert c1.steps_outline == c2.steps_outline
        assert c1.required_tools == c2.required_tools
        assert c1.estimated_complexity == c2.estimated_complexity


def test_13_strategy_id_stability():
    """Test 13: strategy_id is stable across independent DeliberationEngine instances."""
    engine1 = DeliberationEngine()
    engine2 = DeliberationEngine()
    goal = GoalModel(description="Stable strategy id goal", goal_id="goal_stable_123")

    res1 = engine1.deliberate(goal)
    res2 = engine2.deliberate(goal)

    ids1 = [c.strategy_id for c in res1]
    ids2 = [c.strategy_id for c in res2]
    assert ids1 == ids2


def test_14_available_tools_influences_generated_strategies():
    """Test 14: Passing available_tools maps tools into required_tools."""
    engine = DeliberationEngine()
    goal = GoalModel(description="Process dataset file")

    res_no_tools = engine.deliberate(goal, available_tools=None)
    res_tools = engine.deliberate(goal, available_tools=["read_file", "write_file"])

    assert res_no_tools[0].required_tools == []
    assert len(res_tools[0].required_tools) > 0
    assert "read_file" in res_tools[0].required_tools or "write_file" in res_tools[0].required_tools


def test_15_deliberation_engine_side_effect_free():
    """Test 15: DeliberationEngine does not mutate the goal or produce side effects."""
    engine = DeliberationEngine()
    goal = GoalModel(description="Side effect check", priority=1.5)
    orig_status = goal.status
    orig_id = goal.goal_id

    _ = engine.deliberate(goal)

    assert goal.status == orig_status
    assert goal.goal_id == orig_id
    assert goal.priority == 1.5
