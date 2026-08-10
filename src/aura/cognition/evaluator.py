from __future__ import annotations

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

    def evaluate(self, task: AgentTask, observation: Observation) -> EvaluationResult:
        """Evaluates observation success/error status and returns an explicit EvaluationResult."""
        if observation.success:
            return EvaluationResult(
                task_id=task.task_id,
                status=EvaluationStatus.SUCCESS,
                reason=f"Task '{task.description}' completed successfully.",
                observation=observation,
            )

        error_msg = observation.error or f"Task '{task.description}' failed execution."
        return EvaluationResult(
            task_id=task.task_id,
            status=EvaluationStatus.FAILED,
            reason=error_msg,
            observation=observation,
        )
