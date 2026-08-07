from __future__ import annotations

from typing import TYPE_CHECKING

from .goals import AutonomousGoal

if TYPE_CHECKING:
    from ..events import EventBus


class PriorityEngine:
    """Evaluates urgency, importance and user context to score and order goals."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus

    def rank_goals(self, goals: list[AutonomousGoal]) -> list[AutonomousGoal]:
        if not goals:
            return []

        # Sort by priority score descending
        sorted_goals = sorted(goals, key=lambda g: g.priority, reverse=True)

        if self.event_bus is not None and sorted_goals:
            from ..events import GoalPrioritized

            top = sorted_goals[0]
            self.event_bus.publish(
                GoalPrioritized(
                    source="PriorityEngine",
                    goal_id=top.goal_id,
                    priority_score=top.priority,
                )
            )

        return sorted_goals
