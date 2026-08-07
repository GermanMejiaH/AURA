from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from .reasoning import ReasoningResult


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class Intent:
    name: str
    target: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0


@dataclass
class Decision:
    intent: Intent
    approved: bool = True
    reason: str = ""
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=_utcnow)


class DecisionEngine:
    """Evaluates ReasoningResult and produces approved Decision / Intent (SPEC-001 Section 5.6)."""

    def __init__(self, min_confidence: float = 0.5) -> None:
        self.min_confidence = min_confidence

    def evaluate(self, reasoning: ReasoningResult) -> Decision:
        intent = Intent(
            name=reasoning.intent,
            confidence=reasoning.confidence,
            parameters={
                "summary": reasoning.summary,
                "suggested_actions": reasoning.suggested_actions,
            },
        )

        if reasoning.confidence < self.min_confidence:
            return Decision(
                intent=intent,
                approved=False,
                reason=(
                    f"Confidence {reasoning.confidence:.2f} "
                    f"below threshold {self.min_confidence:.2f}"
                ),
            )

        return Decision(
            intent=intent,
            approved=True,
            reason="Approved by DecisionEngine policies",
        )
