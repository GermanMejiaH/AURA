from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    """Execution status for agent goals and multi-step tasks."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"


@dataclass
class AgentGoal:
    """Represents a high-level goal assigned to AURA's autonomous agent system."""

    description: str
    goal_id: str = field(default_factory=lambda: f"goal_{uuid.uuid4().hex[:8]}")
    status: TaskStatus = TaskStatus.PENDING


@dataclass
class AgentTask:
    """Represents a single step or tool action within an AgentPlan."""

    description: str
    order: int = 0
    task_id: str = field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    status: TaskStatus = TaskStatus.PENDING
    tool_name: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: str | None = None


@dataclass
class AgentPlan:
    """Represents a multi-step ordered execution plan for achieving an AgentGoal."""

    goal: AgentGoal
    plan_id: str = field(default_factory=lambda: f"plan_{uuid.uuid4().hex[:8]}")
    tasks: list[AgentTask] = field(default_factory=list)
    replan_count: int = 0
    max_replans: int = 2

    def get_ordered_tasks(self) -> list[AgentTask]:
        """Returns tasks sorted deterministically by their execution order."""
        return sorted(self.tasks, key=lambda t: t.order)

    def get_next_pending_task(self) -> AgentTask | None:
        """Returns the first pending task in execution order, or None if no pending tasks exist."""
        for task in self.get_ordered_tasks():
            if task.status == TaskStatus.PENDING:
                return task
        return None

    def is_completed(self) -> bool:
        """Returns True if the plan has at least one task and all tasks succeeded."""
        if not self.tasks:
            return False
        return all(t.status == TaskStatus.SUCCESS for t in self.tasks)

    def is_failed(self) -> bool:
        """Returns True if any task in the plan has failed."""
        return any(t.status == TaskStatus.FAILED for t in self.tasks)

    def is_waiting_confirmation(self) -> bool:
        """Returns True if any task requires user approval before execution."""
        return any(t.status == TaskStatus.WAITING_CONFIRMATION for t in self.tasks)
