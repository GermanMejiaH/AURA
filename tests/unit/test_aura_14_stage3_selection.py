from __future__ import annotations

import re

import pytest

from aura.cognition.deliberation import (
    GoalModel,
    RiskLevel,
    SimulationOutcome,
    StrategyCandidate,
    StrategySelection,
    StrategySelector,
)


def test_1_selector_constructs():
    """Test 1: StrategySelector initializes cleanly."""
    selector = StrategySelector()
    assert selector.SUCCESS_WEIGHT == 0.60
    assert selector.RISK_WEIGHT == 0.30
    assert selector.COMPLEXITY_WEIGHT == 0.10


def test_2_selects_highest_scoring_strategy():
    """Test 2: Selector chooses the candidate with the highest calculated score."""
    selector = StrategySelector()
    goal = GoalModel(description="Optimize cache")

    c1 = StrategyCandidate(
        strategy_id="s1", name="Direct", description="", estimated_complexity=1.0
    )
    s1 = SimulationOutcome(
        strategy_id="s1", estimated_success_rate=0.90, risk_score=0.10, risk_level=RiskLevel.LOW
    )

    c2 = StrategyCandidate(
        strategy_id="s2", name="Complex", description="", estimated_complexity=4.0
    )
    s2 = SimulationOutcome(
        strategy_id="s2", estimated_success_rate=0.70, risk_score=0.40, risk_level=RiskLevel.MEDIUM
    )

    selection = selector.select(goal, [c1, c2], [s1, s2])

    assert isinstance(selection, StrategySelection)
    assert selection.chosen_strategy.strategy_id == "s1"
    assert selection.chosen_simulation.strategy_id == "s1"


def test_3_success_rate_increases_score():
    """Test 3: Higher success rate yields higher preference when complexity and risk are equal."""
    selector = StrategySelector()
    goal = GoalModel(description="Equal risk comparison")

    c1 = StrategyCandidate(
        strategy_id="s1", name="Low Success", description="", estimated_complexity=1.0
    )
    s1 = SimulationOutcome(
        strategy_id="s1", estimated_success_rate=0.60, risk_score=0.20, risk_level=RiskLevel.LOW
    )

    c2 = StrategyCandidate(
        strategy_id="s2", name="High Success", description="", estimated_complexity=1.0
    )
    s2 = SimulationOutcome(
        strategy_id="s2", estimated_success_rate=0.95, risk_score=0.20, risk_level=RiskLevel.LOW
    )

    selection = selector.select(goal, [c1, c2], [s1, s2])
    assert selection.chosen_strategy.strategy_id == "s2"


def test_4_risk_reduces_score():
    """Test 4: Higher risk score penalizes candidate preference."""
    selector = StrategySelector()
    goal = GoalModel(description="Risk comparison")

    c1 = StrategyCandidate(
        strategy_id="s1", name="High Risk", description="", estimated_complexity=1.0
    )
    s1 = SimulationOutcome(
        strategy_id="s1", estimated_success_rate=0.85, risk_score=0.45, risk_level=RiskLevel.MEDIUM
    )

    c2 = StrategyCandidate(
        strategy_id="s2", name="Low Risk", description="", estimated_complexity=1.0
    )
    s2 = SimulationOutcome(
        strategy_id="s2", estimated_success_rate=0.85, risk_score=0.10, risk_level=RiskLevel.LOW
    )

    selection = selector.select(goal, [c1, c2], [s1, s2])
    assert selection.chosen_strategy.strategy_id == "s2"


def test_5_complexity_reduces_score():
    """Test 5: Higher complexity penalizes candidate preference."""
    selector = StrategySelector()
    goal = GoalModel(description="Complexity comparison")

    c1 = StrategyCandidate(
        strategy_id="s1", name="High Complexity", description="", estimated_complexity=5.0
    )
    s1 = SimulationOutcome(
        strategy_id="s1", estimated_success_rate=0.85, risk_score=0.10, risk_level=RiskLevel.LOW
    )

    c2 = StrategyCandidate(
        strategy_id="s2", name="Low Complexity", description="", estimated_complexity=1.0
    )
    s2 = SimulationOutcome(
        strategy_id="s2", estimated_success_rate=0.85, risk_score=0.10, risk_level=RiskLevel.LOW
    )

    selection = selector.select(goal, [c1, c2], [s1, s2])
    assert selection.chosen_strategy.strategy_id == "s2"


def test_6_low_risk_tolerance_prefers_low_risk():
    """Test 6: LOW risk tolerance rejects HIGH or CRITICAL risk strategies."""
    selector = StrategySelector()
    goal = GoalModel(description="Cautious goal", risk_tolerance=RiskLevel.LOW)

    c1 = StrategyCandidate(
        strategy_id="s1", name="Risky Strategy", description="", estimated_complexity=1.0
    )
    s1 = SimulationOutcome(
        strategy_id="s1", estimated_success_rate=0.99, risk_score=0.60, risk_level=RiskLevel.HIGH
    )

    c2 = StrategyCandidate(
        strategy_id="s2", name="Safe Strategy", description="", estimated_complexity=1.0
    )
    s2 = SimulationOutcome(
        strategy_id="s2", estimated_success_rate=0.75, risk_score=0.15, risk_level=RiskLevel.LOW
    )

    selection = selector.select(goal, [c1, c2], [s1, s2])

    assert selection.chosen_strategy.strategy_id == "s2"
    assert "s1" in selection.rejection_reasons
    assert "exceeds goal risk tolerance LOW" in selection.rejection_reasons["s1"]


def test_7_high_risk_tolerance_allows_high_risk():
    """Test 7: HIGH risk tolerance allows high-risk strategies if success rate is superior."""
    selector = StrategySelector()
    goal = GoalModel(description="Aggressive goal", risk_tolerance=RiskLevel.HIGH)

    c1 = StrategyCandidate(
        strategy_id="s1", name="Aggressive Strategy", description="", estimated_complexity=1.0
    )
    s1 = SimulationOutcome(
        strategy_id="s1", estimated_success_rate=0.99, risk_score=0.35, risk_level=RiskLevel.MEDIUM
    )

    c2 = StrategyCandidate(
        strategy_id="s2", name="Safe Strategy", description="", estimated_complexity=1.0
    )
    s2 = SimulationOutcome(
        strategy_id="s2", estimated_success_rate=0.60, risk_score=0.10, risk_level=RiskLevel.LOW
    )

    selection = selector.select(goal, [c1, c2], [s1, s2])
    assert selection.chosen_strategy.strategy_id == "s1"


def test_8_constraint_no_cmd_rejects_cmd_strategy():
    """Test 8: Constraint 'no_cmd' rejects candidates using cmd tools."""
    selector = StrategySelector()
    goal = GoalModel(description="No cmd goal", constraints=["no_cmd execution"])

    c1 = StrategyCandidate(
        strategy_id="s1",
        name="Cmd Strategy",
        description="",
        required_tools=["cmd"],
        estimated_complexity=1.0,
    )
    s1 = SimulationOutcome(
        strategy_id="s1", estimated_success_rate=0.95, risk_score=0.10, risk_level=RiskLevel.LOW
    )

    c2 = StrategyCandidate(
        strategy_id="s2",
        name="API Strategy",
        description="",
        required_tools=["read_file"],
        estimated_complexity=1.0,
    )
    s2 = SimulationOutcome(
        strategy_id="s2", estimated_success_rate=0.80, risk_score=0.10, risk_level=RiskLevel.LOW
    )

    selection = selector.select(goal, [c1, c2], [s1, s2])

    assert selection.chosen_strategy.strategy_id == "s2"
    assert "s1" in selection.rejection_reasons
    assert "Violates constraint" in selection.rejection_reasons["s1"]


def test_9_constraint_read_only_rejects_write_strategy():
    """Test 9: Constraint 'read_only' rejects candidates using write/modify tools."""
    selector = StrategySelector()
    goal = GoalModel(description="Read only goal", constraints=["read_only mode"])

    c1 = StrategyCandidate(
        strategy_id="s1",
        name="Write Strategy",
        description="",
        required_tools=["write_file"],
        estimated_complexity=1.0,
    )
    s1 = SimulationOutcome(
        strategy_id="s1", estimated_success_rate=0.95, risk_score=0.10, risk_level=RiskLevel.LOW
    )

    c2 = StrategyCandidate(
        strategy_id="s2",
        name="Read Strategy",
        description="",
        required_tools=["read_file"],
        estimated_complexity=1.0,
    )
    s2 = SimulationOutcome(
        strategy_id="s2", estimated_success_rate=0.80, risk_score=0.10, risk_level=RiskLevel.LOW
    )

    selection = selector.select(goal, [c1, c2], [s1, s2])

    assert selection.chosen_strategy.strategy_id == "s2"
    assert "s1" in selection.rejection_reasons


def test_10_incompatible_strategy_is_never_selected():
    """Test 10: Incompatible candidate is recorded in rejection_reasons and not selected."""
    selector = StrategySelector()
    goal = GoalModel(description="Constraint check", constraints=["no_cmd execution"])

    c1 = StrategyCandidate(
        strategy_id="s1",
        name="Cmd Action",
        description="",
        required_tools=["exec_cmd"],
        estimated_complexity=1.0,
    )
    s1 = SimulationOutcome(
        strategy_id="s1", estimated_success_rate=1.0, risk_score=0.0, risk_level=RiskLevel.LOW
    )

    c2 = StrategyCandidate(
        strategy_id="s2",
        name="Safe Action",
        description="",
        required_tools=["inspect"],
        estimated_complexity=2.0,
    )
    s2 = SimulationOutcome(
        strategy_id="s2", estimated_success_rate=0.70, risk_score=0.20, risk_level=RiskLevel.LOW
    )

    selection = selector.select(goal, [c1, c2], [s1, s2])

    assert selection.chosen_strategy.strategy_id == "s2"
    assert "s1" in selection.rejection_reasons


def test_11_all_strategies_incompatible_raises():
    """Test 11: Raises ValueError when all candidates violate constraints or risk limits."""
    selector = StrategySelector()
    goal = GoalModel(
        description="Strict goal", constraints=["no_cmd execution"], risk_tolerance=RiskLevel.LOW
    )

    c1 = StrategyCandidate(
        strategy_id="s1", name="Cmd Action", description="", required_tools=["cmd"]
    )
    s1 = SimulationOutcome(
        strategy_id="s1", estimated_success_rate=0.9, risk_score=0.1, risk_level=RiskLevel.LOW
    )

    c2 = StrategyCandidate(
        strategy_id="s2", name="Risky Action", description="", required_tools=["safe_tool"]
    )
    s2 = SimulationOutcome(
        strategy_id="s2", estimated_success_rate=0.9, risk_score=0.6, risk_level=RiskLevel.HIGH
    )

    with pytest.raises(ValueError, match=re.escape("No viable strategy found for goal")):
        selector.select(goal, [c1, c2], [s1, s2])


def test_12_missing_simulation_raises():
    """Test 12: Raises ValueError when candidates and simulations strategy_ids do not match."""
    selector = StrategySelector()
    goal = GoalModel(description="Mismatch test")

    c1 = StrategyCandidate(strategy_id="s1", name="Strategy 1", description="")
    s2 = SimulationOutcome(
        strategy_id="s2", estimated_success_rate=0.8, risk_score=0.2, risk_level=RiskLevel.LOW
    )

    with pytest.raises(
        ValueError, match=re.escape("Mismatch between candidates and simulations strategy_ids")
    ):
        selector.select(goal, [c1], [s2])


def test_13_unknown_simulation_strategy_raises():
    """Test 13: Empty candidates or simulations list raises ValueError."""
    selector = StrategySelector()
    goal = GoalModel(description="Empty list test")

    c1 = StrategyCandidate(strategy_id="s1", name="Strategy 1", description="")
    s1 = SimulationOutcome(
        strategy_id="s1", estimated_success_rate=0.8, risk_score=0.2, risk_level=RiskLevel.LOW
    )

    with pytest.raises(ValueError, match=re.escape("candidates list cannot be empty")):
        selector.select(goal, [], [s1])

    with pytest.raises(ValueError, match=re.escape("simulations list cannot be empty")):
        selector.select(goal, [c1], [])


def test_14_duplicate_strategy_id_raises():
    """Test 14: Duplicate strategy_id in candidates raises ValueError."""
    selector = StrategySelector()
    goal = GoalModel(description="Duplicate candidate test")

    c1 = StrategyCandidate(strategy_id="s1", name="Strategy A", description="")
    c2 = StrategyCandidate(strategy_id="s1", name="Strategy B", description="")
    s1 = SimulationOutcome(
        strategy_id="s1", estimated_success_rate=0.8, risk_score=0.2, risk_level=RiskLevel.LOW
    )

    with pytest.raises(
        ValueError, match=re.escape("Duplicate strategy_id found in candidates list")
    ):
        selector.select(goal, [c1, c2], [s1])


def test_15_duplicate_simulation_id_raises():
    """Test 15: Duplicate strategy_id in simulations raises ValueError."""
    selector = StrategySelector()
    goal = GoalModel(description="Duplicate simulation test")

    c1 = StrategyCandidate(strategy_id="s1", name="Strategy A", description="")
    s1 = SimulationOutcome(
        strategy_id="s1", estimated_success_rate=0.8, risk_score=0.2, risk_level=RiskLevel.LOW
    )
    s2 = SimulationOutcome(
        strategy_id="s1", estimated_success_rate=0.7, risk_score=0.3, risk_level=RiskLevel.LOW
    )

    with pytest.raises(
        ValueError, match=re.escape("Duplicate strategy_id found in simulations list")
    ):
        selector.select(goal, [c1], [s1, s2])


def test_16_deterministic_tie_breaking():
    """Test 16: Tied score breaks ties deterministically."""
    selector = StrategySelector()
    goal = GoalModel(description="Tie breaking test")

    c1 = StrategyCandidate(
        strategy_id="strat_b", name="B", description="", estimated_complexity=2.0
    )
    s1 = SimulationOutcome(
        strategy_id="strat_b",
        estimated_success_rate=0.80,
        risk_score=0.20,
        risk_level=RiskLevel.LOW,
    )

    c2 = StrategyCandidate(
        strategy_id="strat_a", name="A", description="", estimated_complexity=2.0
    )
    s2 = SimulationOutcome(
        strategy_id="strat_a",
        estimated_success_rate=0.80,
        risk_score=0.20,
        risk_level=RiskLevel.LOW,
    )

    selection = selector.select(goal, [c1, c2], [s1, s2])
    # Tie broken by strategy_id lexicographically smaller: "strat_a" < "strat_b"
    assert selection.chosen_strategy.strategy_id == "strat_a"


def test_17_selection_is_side_effect_free():
    """Test 17: StrategySelector does not mutate goal, candidates, or simulations."""
    selector = StrategySelector()
    goal = GoalModel(description="Side effect check", priority=1.5)

    c1 = StrategyCandidate(strategy_id="s1", name="C1", description="", estimated_complexity=2.0)
    s1 = SimulationOutcome(
        strategy_id="s1", estimated_success_rate=0.85, risk_score=0.15, risk_level=RiskLevel.LOW
    )

    orig_goal_priority = goal.priority
    orig_c1_complexity = c1.estimated_complexity

    _ = selector.select(goal, [c1], [s1])

    assert goal.priority == orig_goal_priority
    assert c1.estimated_complexity == orig_c1_complexity


def test_18_comparison_summary_is_deterministic():
    """Test 18: StrategySelection comparison_summary is reproducible."""
    selector = StrategySelector()
    goal = GoalModel(description="Summary test", constraints=["no_cmd execution"])

    c1 = StrategyCandidate(
        strategy_id="s1", name="Strategy 1", description="", required_tools=["cmd"]
    )
    s1 = SimulationOutcome(
        strategy_id="s1", estimated_success_rate=0.95, risk_score=0.10, risk_level=RiskLevel.LOW
    )

    c2 = StrategyCandidate(
        strategy_id="s2", name="Strategy 2", description="", required_tools=["read_file"]
    )
    s2 = SimulationOutcome(
        strategy_id="s2", estimated_success_rate=0.80, risk_score=0.15, risk_level=RiskLevel.LOW
    )

    selection1 = selector.select(goal, [c1, c2], [s1, s2])
    selection2 = selector.select(goal, [c1, c2], [s1, s2])

    assert selection1.comparison_summary == selection2.comparison_summary
    assert "Selected strategy 's2'" in selection1.comparison_summary
    assert (
        "Strategy 's1' rejected: Violates constraint 'no_cmd execution'."
        in selection1.comparison_summary
    )
