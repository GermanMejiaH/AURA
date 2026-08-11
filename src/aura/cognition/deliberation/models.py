from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ...autonomy.agent_models import AgentGoal


class RiskLevel(str, Enum):
    """Risk severity classification for goal deliberation and strategy simulation."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class GoalModel(AgentGoal):
    """Enriched goal representation with priorities, constraints, and risk tolerance."""

    priority: float = 1.0
    constraints: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    risk_tolerance: RiskLevel = RiskLevel.MEDIUM
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.priority < 0.0:
            raise ValueError("priority must be >= 0.0")


@dataclass
class StrategyCandidate:
    """Represents a proposed strategic approach to fulfill a GoalModel."""

    strategy_id: str
    name: str
    description: str
    steps_outline: list[str] = field(default_factory=list)
    required_tools: list[str] = field(default_factory=list)
    estimated_complexity: float = 1.0

    def __post_init__(self) -> None:
        if not (1.0 <= self.estimated_complexity <= 5.0):
            raise ValueError("estimated_complexity must be between 1.0 and 5.0")


@dataclass
class SimulationOutcome:
    """Outcome simulation result evaluating risks and success rate of a candidate strategy."""

    strategy_id: str
    estimated_success_rate: float
    risk_score: float
    risk_level: RiskLevel
    potential_bottlenecks: list[str] = field(default_factory=list)
    matched_lessons: list[str] = field(default_factory=list)
    explanation: str = ""

    def __post_init__(self) -> None:
        if not (0.0 <= self.estimated_success_rate <= 1.0):
            raise ValueError("estimated_success_rate must be between 0.0 and 1.0")
        if not (0.0 <= self.risk_score <= 1.0):
            raise ValueError("risk_score must be between 0.0 and 1.0")


@dataclass
class StrategySelection:
    """Encapsulates the optimal strategy selected after evaluating all candidates."""

    goal_id: str
    chosen_strategy: StrategyCandidate
    chosen_simulation: SimulationOutcome
    all_candidates: list[StrategyCandidate] = field(default_factory=list)
    comparison_summary: str = ""
    rejection_reasons: dict[str, str] = field(default_factory=dict)
