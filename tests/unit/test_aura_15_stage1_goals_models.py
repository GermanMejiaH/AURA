from __future__ import annotations

import pytest

from aura.cognition.deliberation import DeliberationEngine, GoalModel, RiskLevel
from aura.cognition.goals import (
    GoalContextRef,
    GoalPriority,
    GoalProgress,
    GoalStatus,
    PersistentGoal,
)


def test_1_persistent_goal_initialization_defaults():
    """Test 1: PersistentGoal initializes with sensible defaults."""
    goal = PersistentGoal(description="Organize workspace desk")

    assert goal.goal_id.startswith("pgoal_")
    assert goal.description == "Organize workspace desk"
    assert goal.priority == GoalPriority.MEDIUM
    assert goal.status == GoalStatus.PENDING
    assert isinstance(goal.progress, GoalProgress)
    assert goal.progress.completion_percentage == 0.0
    assert isinstance(goal.context, GoalContextRef)
    assert goal.parent_goal_id is None
    assert goal.risk_tolerance == RiskLevel.MEDIUM


def test_2_empty_description_raises_value_error():
    """Test 2: Instantiating PersistentGoal with empty description raises ValueError."""
    with pytest.raises(ValueError, match="description cannot be empty"):
        PersistentGoal(description="")


def test_3_goal_status_transitions():
    """Test 3: PersistentGoal status updates update updated_at timestamp."""
    goal = PersistentGoal(description="Clean repository")
    orig_updated = goal.updated_at

    goal.set_status(GoalStatus.ACTIVE)
    assert goal.status == GoalStatus.ACTIVE
    assert goal.updated_at >= orig_updated


def test_4_goal_priority_numeric_weights():
    """Test 4: GoalPriority enum returns correct numeric weights."""
    assert GoalPriority.LOW.numeric_weight == 1.0
    assert GoalPriority.MEDIUM.numeric_weight == 2.0
    assert GoalPriority.HIGH.numeric_weight == 3.0
    assert GoalPriority.CRITICAL.numeric_weight == 4.0


def test_5_goal_progress_updates():
    """Test 5: GoalProgress bounds percentage (0-100) and tracks milestones."""
    progress = GoalProgress()
    progress.update(percentage=150.0, add_milestone="Phase 1 complete", notes="Halfway done")

    assert progress.completion_percentage == 100.0
    assert "Phase 1 complete" in progress.milestones_completed
    assert progress.notes == "Halfway done"

    progress.update(percentage=-20.0)
    assert progress.completion_percentage == 0.0


def test_6_goal_context_ref_fields():
    """Test 6: GoalContextRef stores location, entities, tags, and metadata."""
    ctx = GoalContextRef(
        location="office_room",
        entities=["laptop", "notebook"],
        tags=["cleaning", "organization"],
        metadata={"owner": "Andres"},
    )
    assert ctx.location == "office_room"
    assert "laptop" in ctx.entities
    assert ctx.metadata["owner"] == "Andres"


def test_7_to_goal_model_projection():
    """Test 7: PersistentGoal projects cleanly into a GoalModel for AURA 1.4 deliberation."""
    pgoal = PersistentGoal(
        description="Deploy software build",
        priority=GoalPriority.HIGH,
        constraints=["no_downtime"],
        success_criteria=["build_passes"],
        risk_tolerance=RiskLevel.LOW,
    )
    model = pgoal.to_goal_model()

    assert isinstance(model, GoalModel)
    assert model.goal_id == pgoal.goal_id
    assert model.description == pgoal.description
    assert model.priority == 3.0
    assert "no_downtime" in model.constraints
    assert "build_passes" in model.success_criteria
    assert model.risk_tolerance == RiskLevel.LOW
    assert "pgoal_" in model.metadata["context_summary"]


def test_8_persistent_goal_deliberation_compatibility():
    """Test 8: Projected GoalModel works seamlessly with DeliberationEngine."""
    pgoal = PersistentGoal(description="Archive old logs")
    engine = DeliberationEngine()
    candidates = engine.deliberate(pgoal.to_goal_model())

    assert len(candidates) >= 1
    assert candidates[0].strategy_id.startswith("strat_")
