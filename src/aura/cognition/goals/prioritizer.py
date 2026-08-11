from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from .models import GoalPriority, GoalStatus, PersistentGoal


@dataclass
class PrioritizedGoal:
    """Represents a PersistentGoal evaluated, scored, and ranked deterministically."""

    goal: PersistentGoal
    score: float
    rank: int
    explanation: str


class GoalPrioritizer:
    """Pure, deterministic scoring engine for ranking PersistentGoals."""

    PRIORITY_WEIGHTS: ClassVar[dict[GoalPriority, float]] = {
        GoalPriority.CRITICAL: 40.0,
        GoalPriority.HIGH: 30.0,
        GoalPriority.MEDIUM: 20.0,
        GoalPriority.LOW: 10.0,
    }

    STATUS_WEIGHTS: ClassVar[dict[GoalStatus, float]] = {
        GoalStatus.ACTIVE: 15.0,
        GoalStatus.PENDING: 10.0,
        GoalStatus.BLOCKED: 5.0,
        GoalStatus.PAUSED: 0.0,
        GoalStatus.COMPLETED: -50.0,
        GoalStatus.FAILED: -50.0,
        GoalStatus.CANCELLED: -100.0,
    }

    def prioritize(self, goals: list[PersistentGoal]) -> list[PrioritizedGoal]:
        """Calculates score, rank, and explanation for PersistentGoals deterministically."""
        if not goals:
            return []

        scored_items: list[tuple[float, str, str, PersistentGoal, str]] = []

        for g in goals:
            p_weight = self.PRIORITY_WEIGHTS.get(g.priority, 20.0)
            s_weight = self.STATUS_WEIGHTS.get(g.status, 0.0)

            # Terminal states do not receive remaining progress bonus
            if g.status in (GoalStatus.COMPLETED, GoalStatus.FAILED, GoalStatus.CANCELLED):
                prog_weight = 0.0
            else:
                remaining_percent = max(0.0, 100.0 - g.progress.completion_percentage)
                prog_weight = remaining_percent * 0.1

            total_score = round(p_weight + s_weight + prog_weight, 2)

            explanation = (
                f"Priority {g.priority.value} ({p_weight:.1f}); "
                f"Status {g.status.value} ({s_weight:+.1f}); "
                f"Remaining progress (+{prog_weight:.1f})"
            )

            scored_items.append((total_score, g.created_at, g.goal_id, g, explanation))

        # Deterministic sorting: highest score (-score), oldest created_at, tie-break by goal_id
        scored_items.sort(key=lambda item: (-item[0], item[1], item[2]))

        result: list[PrioritizedGoal] = []
        for rank, (score, _, _, goal, explanation) in enumerate(scored_items, start=1):
            result.append(
                PrioritizedGoal(
                    goal=goal,
                    score=score,
                    rank=rank,
                    explanation=explanation,
                )
            )

        return result
