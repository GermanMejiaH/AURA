from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from aura.cognition.deliberation.models import GoalModel, RiskLevel


class GoalStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class GoalPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @property
    def numeric_weight(self) -> float:
        weights = {
            GoalPriority.LOW: 1.0,
            GoalPriority.MEDIUM: 2.0,
            GoalPriority.HIGH: 3.0,
            GoalPriority.CRITICAL: 4.0,
        }
        return weights.get(self, 2.0)


@dataclass
class GoalProgress:
    completion_percentage: float = 0.0
    milestones_completed: list[str] = field(default_factory=list)
    last_updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    notes: str = ""

    def update(
        self,
        percentage: float | None = None,
        add_milestone: str | None = None,
        notes: str | None = None,
    ) -> None:
        if percentage is not None:
            self.completion_percentage = max(0.0, min(100.0, percentage))
        if add_milestone and add_milestone not in self.milestones_completed:
            self.milestones_completed.append(add_milestone)
        if notes is not None:
            self.notes = notes
        self.last_updated_at = datetime.now(UTC).isoformat()


@dataclass
class GoalContextRef:
    location: str | None = None
    entities: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PersistentGoal:
    description: str
    goal_id: str = field(default_factory=lambda: f"pgoal_{uuid.uuid4().hex[:8]}")
    priority: GoalPriority = GoalPriority.MEDIUM
    status: GoalStatus = GoalStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    success_criteria: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    context: GoalContextRef = field(default_factory=GoalContextRef)
    progress: GoalProgress = field(default_factory=GoalProgress)
    parent_goal_id: str | None = None
    risk_tolerance: RiskLevel = RiskLevel.MEDIUM

    def __post_init__(self) -> None:
        if not self.description:
            raise ValueError("PersistentGoal description cannot be empty.")

    def set_status(self, new_status: GoalStatus) -> None:
        self.status = new_status
        self.updated_at = datetime.now(UTC).isoformat()

    def to_goal_model(self) -> GoalModel:
        return GoalModel(
            goal_id=self.goal_id,
            description=self.description,
            priority=self.priority.numeric_weight,
            constraints=list(self.constraints),
            success_criteria=list(self.success_criteria),
            risk_tolerance=self.risk_tolerance,
            metadata={
                "context_summary": (
                    f"PersistentGoal(id={self.goal_id}, "
                    f"status={self.status.value}, "
                    f"progress={self.progress.completion_percentage}%)"
                )
            },
        )
