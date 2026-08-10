from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..autonomy.agent_models import AgentTask
    from ..autonomy.observation import Observation


class EvaluationStatus(str, Enum):
    """Status representing the deterministic evaluation of a task execution observation."""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REPLAN_REQUIRED = "REPLAN_REQUIRED"


@dataclass
class EvaluationResult:
    """Encapsulates the evaluation output for a single AgentTask execution observation."""

    task_id: str
    status: EvaluationStatus
    reason: str
    observation: Observation


class TaskEvaluator:
    """Evaluates task execution observations deterministically without making direct LLM calls."""

    UNRECOVERABLE_PATTERNS: tuple[str, ...] = (
        "unrecoverable",
        "fatal",
        "permission denied",
        "access denied",
    )

    RECOVERABLE_PATTERNS: tuple[str, ...] = (
        "retry",
        "invalid parameter",
        "missing parameter",
        "replan",
    )

    def evaluate(
        self,
        task: AgentTask,
        observation: Observation,
        recoverable: bool | None = None,
    ) -> EvaluationResult:
        """Evaluates observation success/error status and returns an explicit EvaluationResult."""
        if observation.success:
            return EvaluationResult(
                task_id=task.task_id,
                status=EvaluationStatus.SUCCESS,
                reason=f"Task '{task.description}' completed successfully.",
                observation=observation,
            )

        error_msg = observation.error or f"Task '{task.description}' failed execution."
        err_lower = error_msg.lower()

        # Check explicit setting first
        if recoverable is not None:
            is_rec = recoverable
        elif observation.metadata.get("recoverable") is not None:
            is_rec = bool(observation.metadata.get("recoverable"))
        elif any(unrec in err_lower for unrec in self.UNRECOVERABLE_PATTERNS):
            is_rec = False
        elif re.search(r"\brecoverable\b", err_lower):
            is_rec = True
        else:
            is_rec = any(pat in err_lower for pat in self.RECOVERABLE_PATTERNS)

        status = EvaluationStatus.REPLAN_REQUIRED if is_rec else EvaluationStatus.FAILED

        return EvaluationResult(
            task_id=task.task_id,
            status=status,
            reason=error_msg,
            observation=observation,
        )
