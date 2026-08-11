from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from .models import GoalStatus, PersistentGoal
from .prioritizer import PrioritizedGoal


@dataclass
class SelectedGoal:
    """Represents the single top-priority eligible goal selected for execution planning."""

    goal: PersistentGoal
    score: float
    rank: int
    selection_reason: str


class GoalSelector:
    """Pure, deterministic selection engine filtering and choosing the active goal."""

    INELIGIBLE_STATUSES: ClassVar[set[GoalStatus]] = {
        GoalStatus.COMPLETED,
        GoalStatus.FAILED,
        GoalStatus.CANCELLED,
        GoalStatus.PAUSED,
        GoalStatus.BLOCKED,
    }

    def select_goal(self, prioritized_goals: list[PrioritizedGoal]) -> SelectedGoal | None:
        """Selects the highest ranked eligible goal from prioritized goals deterministically."""
        if not prioritized_goals:
            return None

        for pg in prioritized_goals:
            if pg.goal.status not in self.INELIGIBLE_STATUSES:
                reason = (
                    f"Selected rank #{pg.rank} (score {pg.score:.1f}, "
                    f"status {pg.goal.status.value}): '{pg.goal.description}'"
                )
                return SelectedGoal(
                    goal=pg.goal,
                    score=pg.score,
                    rank=pg.rank,
                    selection_reason=reason,
                )

        return None
