from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from .decision import Decision


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class PlanStep:
    name: str
    action_type: str
    target: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))
    completed: bool = False
    error: str | None = None


@dataclass
class Plan:
    goal: str
    steps: list[PlanStep] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=_utcnow)

    @property
    def is_complete(self) -> bool:
        return all(s.completed for s in self.steps) if self.steps else True


class Planner:
    """Decomposes Decision / Intent into executable Plan steps (SPEC-001 Section 5.7)."""

    def create_plan(self, decision: Decision) -> Plan:
        intent = decision.intent
        steps: list[PlanStep] = []

        if not decision.approved:
            steps.append(
                PlanStep(
                    name="notify_decision_rejected",
                    action_type="speak",
                    parameters={"text": f"Acción cancelada: {decision.reason}"},
                )
            )
            return Plan(goal=f"rejected:{intent.name}", steps=steps)

        suggested = intent.parameters.get("suggested_actions", [])
        if suggested:
            for i, act in enumerate(suggested):
                steps.append(
                    PlanStep(
                        name=act.get("name", f"step_{i+1}"),
                        action_type=act.get("type", "execute"),
                        target=act.get("target", ""),
                        parameters=act.get("parameters", {}),
                    )
                )
        else:
            # Default step for intent
            steps.append(
                PlanStep(
                    name=f"execute_{intent.name}",
                    action_type="speak" if intent.name == "general_response" else "execute",
                    target=intent.target,
                    parameters=intent.parameters,
                )
            )

        return Plan(goal=intent.name, steps=steps)
