from __future__ import annotations

import json
from unittest.mock import MagicMock

from aura.cognition.deliberation import (
    GoalModel,
    OutcomeSimulator,
    RiskLevel,
    StrategyCandidate,
)
from aura.memory.episodic import Episode
from aura.memory.retrieval import MemoryResult, MemoryRetriever


def _create_mock_retriever(results: list[MemoryResult] | None = None) -> MemoryRetriever:
    retriever = MagicMock(spec=MemoryRetriever)
    retriever.search.return_value = results or []
    return retriever


def test_1_simulator_constructs_successful_outcome():
    """Test 1: Baseline simulation produces a successful high success rate outcome."""
    retriever = _create_mock_retriever()
    simulator = OutcomeSimulator(retriever)
    goal = GoalModel(description="Clean database cache")
    strategy = StrategyCandidate(
        strategy_id="strat_001",
        name="Direct Cache Clear",
        description="Flushes redis cache directly",
        estimated_complexity=1.0,
    )

    outcome = simulator.simulate(strategy, goal)
    assert outcome.strategy_id == "strat_001"
    assert outcome.estimated_success_rate == 0.80
    assert outcome.risk_score == 0.20
    assert outcome.risk_level == RiskLevel.LOW


def test_2_simulator_constructs_low_risk_outcome():
    """Test 2: Low risk score (<0.25) resolves to RiskLevel.LOW."""
    retriever = _create_mock_retriever()
    simulator = OutcomeSimulator(retriever)
    goal = GoalModel(description="Simple test")
    strategy = StrategyCandidate(
        strategy_id="s_low",
        name="Low Risk Strategy",
        description="Desc",
        estimated_complexity=1.0,
    )

    outcome = simulator.simulate(strategy, goal)
    assert outcome.risk_score < 0.25
    assert outcome.risk_level == RiskLevel.LOW


def test_3_simulator_constructs_high_risk_outcome():
    """Test 3: Risk score between 0.50 and 0.75 resolves to RiskLevel.HIGH."""
    ep_details = json.dumps(
        {
            "outcome": "FAILED",
            "verification_status": "FATAL_FAILURE",
            "root_cause": "Database connection timeout under heavy lock",
            "tools_used": ["db_exec"],
        }
    )
    ep = Episode(id="ep1", summary="Failed db query", details=ep_details)
    mem_res = MemoryResult(episode=ep, score=0.9)
    retriever = _create_mock_retriever([mem_res])

    simulator = OutcomeSimulator(retriever)
    goal = GoalModel(description="Run heavy db script", risk_tolerance=RiskLevel.LOW)
    strategy = StrategyCandidate(
        strategy_id="s_high",
        name="Heavy DB Strategy",
        description="Desc",
        required_tools=["db_exec"],
        estimated_complexity=4.0,
    )

    outcome = simulator.simulate(strategy, goal)
    assert 0.50 <= outcome.risk_score < 0.75
    assert outcome.risk_level == RiskLevel.HIGH


def test_4_simulator_constructs_critical_risk_outcome():
    """Test 4: High risk accumulated score (>=0.75) resolves to RiskLevel.CRITICAL."""
    ep1_details = json.dumps(
        {
            "outcome": "FAILED",
            "verification_status": "FATAL_FAILURE",
            "root_cause": "System crash due to kernel overflow",
            "lesson_learned": "Never run raw cmd on production root",
            "tools_used": ["cmd"],
        }
    )
    ep2_details = json.dumps(
        {
            "outcome": "FAILED",
            "verification_status": "FATAL_FAILURE",
            "root_cause": "Disk partition wiped accidentally",
            "lesson_learned": "Always double check root permissions",
            "tools_used": ["cmd"],
        }
    )
    ep1 = Episode(id="ep1", summary="Crash 1", details=ep1_details)
    ep2 = Episode(id="ep2", summary="Crash 2", details=ep2_details)
    retriever = _create_mock_retriever(
        [
            MemoryResult(episode=ep1, score=0.9),
            MemoryResult(episode=ep2, score=0.85),
        ]
    )

    simulator = OutcomeSimulator(retriever)
    goal = GoalModel(
        description="Execute system command",
        constraints=["no_cmd execution"],
        risk_tolerance=RiskLevel.LOW,
    )
    strategy = StrategyCandidate(
        strategy_id="s_crit",
        name="Raw Cmd Exec",
        description="Desc",
        required_tools=["cmd"],
        estimated_complexity=5.0,
    )

    outcome = simulator.simulate(strategy, goal)
    assert outcome.risk_score >= 0.75
    assert outcome.risk_level == RiskLevel.CRITICAL


def test_5_success_rate_is_bounded():
    """Test 5: Success rate is clamped to [0.0, 1.0]."""
    retriever = _create_mock_retriever()
    simulator = OutcomeSimulator(retriever)
    goal = GoalModel(description="Bound test")
    strategy = StrategyCandidate(
        strategy_id="s_bnd",
        name="Name",
        description="Desc",
        estimated_complexity=1.0,
    )

    outcome = simulator.simulate(strategy, goal)
    assert 0.0 <= outcome.estimated_success_rate <= 1.0


def test_6_risk_score_is_bounded():
    """Test 6: Risk score is clamped to [0.0, 1.0]."""
    retriever = _create_mock_retriever()
    simulator = OutcomeSimulator(retriever)
    goal = GoalModel(description="Bound test")
    strategy = StrategyCandidate(
        strategy_id="s_bnd2",
        name="Name",
        description="Desc",
        estimated_complexity=1.0,
    )

    outcome = simulator.simulate(strategy, goal)
    assert 0.0 <= outcome.risk_score <= 1.0


def test_7_historical_lesson_reduces_success_rate():
    """Test 7: Matching historical lesson reduces estimated_success_rate."""
    ep_details = json.dumps(
        {"lesson_learned": "Rate limit exceeded when calling API without delay"}
    )
    ep = Episode(id="ep_l", summary="API issue", details=ep_details)
    retriever = _create_mock_retriever([MemoryResult(episode=ep, score=0.8)])

    simulator = OutcomeSimulator(retriever)
    goal = GoalModel(description="Fetch API data")
    strategy = StrategyCandidate(
        strategy_id="s_api",
        name="Direct API Fetch",
        description="Desc",
        estimated_complexity=1.0,
    )

    outcome = simulator.simulate(strategy, goal)
    assert outcome.estimated_success_rate < 0.80
    assert len(outcome.matched_lessons) == 1


def test_8_historical_root_cause_increases_risk():
    """Test 8: Matching historical root cause increases risk_score."""
    ep_details = json.dumps({"root_cause": "Network socket closed by remote peer"})
    ep = Episode(id="ep_rc", summary="Socket failure", details=ep_details)
    retriever = _create_mock_retriever([MemoryResult(episode=ep, score=0.8)])

    simulator = OutcomeSimulator(retriever)
    goal = GoalModel(description="Open socket connection")
    strategy = StrategyCandidate(
        strategy_id="s_sock",
        name="Raw Socket Connect",
        description="Desc",
        estimated_complexity=1.0,
    )

    outcome = simulator.simulate(strategy, goal)
    assert outcome.risk_score > 0.20
    assert len(outcome.potential_bottlenecks) >= 1


def test_9_repeated_failures_increase_risk():
    """Test 9: Repeated failed episodes increase risk_score."""
    ep1 = Episode(id="e1", summary="Fail 1", details=json.dumps({"outcome": "FAILED"}))
    ep2 = Episode(
        id="e2", summary="Fail 2", details=json.dumps({"verification_status": "FATAL_FAILURE"})
    )
    retriever = _create_mock_retriever(
        [
            MemoryResult(episode=ep1, score=0.8),
            MemoryResult(episode=ep2, score=0.7),
        ]
    )

    simulator = OutcomeSimulator(retriever)
    goal = GoalModel(description="Retry operation")
    strategy = StrategyCandidate(
        strategy_id="s_fail",
        name="Flaky Strategy",
        description="Desc",
        estimated_complexity=1.0,
    )

    outcome = simulator.simulate(strategy, goal)
    assert outcome.risk_score > 0.20


def test_10_matching_lessons_are_returned():
    """Test 10: Matched lessons list is returned in SimulationOutcome."""
    ep_details = json.dumps({"lesson_learned": "Always sanitize user inputs"})
    ep = Episode(id="ep_val", summary="Validation error", details=ep_details)
    retriever = _create_mock_retriever([MemoryResult(episode=ep, score=0.8)])

    simulator = OutcomeSimulator(retriever)
    goal = GoalModel(description="Process form input")
    strategy = StrategyCandidate(
        strategy_id="s_val",
        name="Form Processor",
        description="Desc",
        estimated_complexity=1.0,
    )

    outcome = simulator.simulate(strategy, goal)
    assert "Always sanitize user inputs" in outcome.matched_lessons


def test_11_no_historical_match_preserves_baseline():
    """Test 11: Empty memory search preserves baseline success rate and risk score."""
    retriever = _create_mock_retriever([])
    simulator = OutcomeSimulator(retriever)
    goal = GoalModel(description="Brand new unrecorded goal")
    strategy = StrategyCandidate(
        strategy_id="s_clean",
        name="New Approach",
        description="Desc",
        estimated_complexity=1.0,
    )

    outcome = simulator.simulate(strategy, goal)
    assert outcome.estimated_success_rate == 0.80
    assert outcome.risk_score == 0.20
    assert outcome.matched_lessons == []
    assert outcome.potential_bottlenecks == []


def test_12_complexity_affects_risk():
    """Test 12: Higher complexity candidate receives higher initial risk score."""
    retriever = _create_mock_retriever()
    simulator = OutcomeSimulator(retriever)
    goal = GoalModel(description="Complexity evaluation")

    strat_simple = StrategyCandidate(
        strategy_id="s_sim",
        name="Simple",
        description="Desc",
        estimated_complexity=1.0,
    )
    strat_complex = StrategyCandidate(
        strategy_id="s_cpx",
        name="Complex",
        description="Desc",
        estimated_complexity=5.0,
    )

    out_simple = simulator.simulate(strat_simple, goal)
    out_complex = simulator.simulate(strat_complex, goal)

    assert out_complex.risk_score > out_simple.risk_score


def test_13_simulation_is_deterministic():
    """Test 13: Identical inputs produce identical SimulationOutcome attributes."""
    retriever = _create_mock_retriever()
    simulator = OutcomeSimulator(retriever)
    goal = GoalModel(description="Determinism test", goal_id="g_det")
    strategy = StrategyCandidate(
        strategy_id="s_det",
        name="Strategy Det",
        description="Desc",
        estimated_complexity=2.0,
    )

    out1 = simulator.simulate(strategy, goal)
    out2 = simulator.simulate(strategy, goal)

    assert out1.strategy_id == out2.strategy_id
    assert out1.estimated_success_rate == out2.estimated_success_rate
    assert out1.risk_score == out2.risk_score
    assert out1.risk_level == out2.risk_level
    assert out1.matched_lessons == out2.matched_lessons
    assert out1.potential_bottlenecks == out2.potential_bottlenecks
    assert out1.explanation == out2.explanation


def test_14_simulation_has_no_side_effects():
    """Test 14: Simulator does not mutate goal, strategy, or memory retriever state."""
    retriever = _create_mock_retriever()
    simulator = OutcomeSimulator(retriever)
    goal = GoalModel(description="Side effect check", priority=2.0)
    strategy = StrategyCandidate(
        strategy_id="s_se",
        name="Strategy SE",
        description="Desc",
        estimated_complexity=1.5,
    )

    orig_goal_priority = goal.priority
    orig_strat_complexity = strategy.estimated_complexity

    _ = simulator.simulate(strategy, goal)

    assert goal.priority == orig_goal_priority
    assert strategy.estimated_complexity == orig_strat_complexity
    assert retriever.search.call_count == 1


def test_15_missing_memory_results_are_safe():
    """Test 15: Exceptions inside MemoryRetriever search are caught safely without crashing."""
    retriever = MagicMock(spec=MemoryRetriever)
    retriever.search.side_effect = RuntimeError("Database locked")

    simulator = OutcomeSimulator(retriever)
    goal = GoalModel(description="Failing retriever goal")
    strategy = StrategyCandidate(
        strategy_id="s_err",
        name="Strategy Error",
        description="Desc",
        estimated_complexity=1.0,
    )

    outcome = simulator.simulate(strategy, goal)
    assert outcome.estimated_success_rate == 0.80
    assert outcome.risk_score == 0.20


def test_16_legacy_episodes_are_supported():
    """Test 16: Legacy episodes with missing/corrupted JSON details do not cause exceptions."""
    ep_legacy1 = Episode(id="leg1", summary="Legacy ep 1", details=None)
    ep_legacy2 = Episode(id="leg2", summary="Legacy ep 2", details="{invalid_json")
    ep_legacy3 = Episode(id="leg3", summary="Legacy ep 3", details='{"old_format": 123}')

    retriever = _create_mock_retriever(
        [
            MemoryResult(episode=ep_legacy1, score=0.8),
            MemoryResult(episode=ep_legacy2, score=0.7),
            MemoryResult(episode=ep_legacy3, score=0.6),
        ]
    )

    simulator = OutcomeSimulator(retriever)
    goal = GoalModel(description="Legacy compatibility test")
    strategy = StrategyCandidate(
        strategy_id="s_leg",
        name="Legacy Compatible",
        description="Desc",
        estimated_complexity=1.0,
    )

    outcome = simulator.simulate(strategy, goal)
    assert outcome.estimated_success_rate == 0.80
    assert outcome.risk_score == 0.20


def test_17_risk_level_matches_risk_score():
    """Test 17: Private _determine_risk_level correctly maps risk scores to RiskLevel."""
    retriever = _create_mock_retriever()
    simulator = OutcomeSimulator(retriever)

    assert simulator._determine_risk_level(0.10) == RiskLevel.LOW
    assert simulator._determine_risk_level(0.35) == RiskLevel.MEDIUM
    assert simulator._determine_risk_level(0.60) == RiskLevel.HIGH
    assert simulator._determine_risk_level(0.85) == RiskLevel.CRITICAL


def test_18_simulation_outcome_contains_explanation():
    """Test 18: SimulationOutcome explanation contains clear descriptive feedback."""
    retriever = _create_mock_retriever()
    simulator = OutcomeSimulator(retriever)
    goal = GoalModel(description="Explanation check")
    strategy = StrategyCandidate(
        strategy_id="s_exp",
        name="Direct Action",
        description="Desc",
        estimated_complexity=1.0,
    )

    outcome = simulator.simulate(strategy, goal)
    assert isinstance(outcome.explanation, str)
    assert "Strategy 'Direct Action':" in outcome.explanation
