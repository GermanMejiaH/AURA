from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .goals import AutonomousGoal

if TYPE_CHECKING:
    from ..events import EventBus


@dataclass
class SubGoal:
    description: str
    id: str = field(default_factory=lambda: f"sub_{uuid.uuid4().hex[:6]}")
    completed: bool = False


class LongHorizonPlanner:
    """Decomposes high-level complex goals into multi-step long-term plans."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus

    def generate_plan(self, goal: AutonomousGoal) -> list[SubGoal]:
        subgoals = [
            SubGoal(description=f"Analizar contexto para '{goal.description}'"),
            SubGoal(description=f"Ejecutar pasos principales de '{goal.description}'"),
            SubGoal(description=f"Verificar cumplimiento de '{goal.description}'"),
        ]
        goal.subgoals = [sub.id for sub in subgoals]

        if self.event_bus is not None:
            from ..events import LongPlanGenerated

            self.event_bus.publish(
                LongPlanGenerated(
                    source="LongHorizonPlanner",
                    goal_id=goal.goal_id,
                    subgoal_count=len(subgoals),
                )
            )

        return subgoals
