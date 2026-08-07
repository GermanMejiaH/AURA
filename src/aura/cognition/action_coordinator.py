from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .planner import Plan, PlanStep

if TYPE_CHECKING:
    from ..events import EventBus


@dataclass
class ActionResult:
    step_id: str
    success: bool
    message: str = ""
    data: dict[str, Any] | None = None


class ActionCoordinator:
    """Dispatches plan steps to target modules and tracks execution (SPEC-001 Section 5.8)."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus

    def execute_plan(self, plan: Plan) -> list[ActionResult]:
        results: list[ActionResult] = []

        for step in plan.steps:
            res = self.execute_step(step, plan_id=plan.id)
            results.append(res)
            if not res.success:
                break

        return results

    def execute_step(self, step: PlanStep, plan_id: str = "") -> ActionResult:
        if self.event_bus is not None:
            from ..events import ActionDispatched, StepExecuted

            self.event_bus.publish(
                ActionDispatched(
                    source="ActionCoordinator",
                    action_id=step.id,
                    action_type=step.action_type,
                    target=step.target,
                )
            )

            step.completed = True
            result = ActionResult(
                step_id=step.id,
                success=True,
                message=f"Action '{step.name}' dispatched via EventBus",
            )

            self.event_bus.publish(
                StepExecuted(
                    source="ActionCoordinator",
                    plan_id=plan_id,
                    step_id=step.id,
                    success=True,
                    result=result.message,
                )
            )
            return result

        step.completed = True
        return ActionResult(
            step_id=step.id,
            success=True,
            message=f"Action '{step.name}' executed locally",
        )
