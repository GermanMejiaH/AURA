from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..events import EventBus


@dataclass
class AutonomousGoal:
    description: str
    goal_id: str = field(default_factory=lambda: f"goal_{uuid.uuid4().hex[:8]}")
    priority: float = 1.0
    status: str = "pending"  # pending, active, achieved, failed
    created_at: float = field(default_factory=time.time)
    subgoals: list[str] = field(default_factory=list)


class GoalManager:
    """Manages high-level autonomous goal lifecycle, tracking & status updates."""

    def __init__(
        self,
        event_bus: EventBus | None = None,
        container: Any | None = None,
    ) -> None:
        self.event_bus = event_bus
        self._goals: dict[str, AutonomousGoal] = {}

    def create_goal(self, description: str, priority: float = 1.0) -> AutonomousGoal:
        goal = AutonomousGoal(description=description, priority=priority)
        self._goals[goal.goal_id] = goal

        if self.event_bus is not None:
            from ..events import GoalStatusChanged

            self.event_bus.publish(
                GoalStatusChanged(
                    source="GoalManager",
                    goal_id=goal.goal_id,
                    status=goal.status,
                )
            )
        return goal

    def get_goal(self, goal_id: str) -> AutonomousGoal | None:
        return self._goals.get(goal_id)

    def get_active_goals(self) -> list[AutonomousGoal]:
        return [g for g in self._goals.values() if g.status in ("pending", "active")]

    def update_status(self, goal_id: str, new_status: str) -> bool:
        goal = self.get_goal(goal_id)
        if goal is None:
            return False

        goal.status = new_status
        if self.event_bus is not None:
            from ..events import GoalStatusChanged

            self.event_bus.publish(
                GoalStatusChanged(
                    source="GoalManager",
                    goal_id=goal_id,
                    status=new_status,
                )
            )
        return True
