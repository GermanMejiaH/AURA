from __future__ import annotations

import threading
from dataclasses import dataclass, field

from ..events import (
    AgentConfirmationDenied,
    AgentConfirmationGranted,
    AgentPlanCompleted,
    AgentPlanCreated,
    AgentReplanFailed,
    AgentReplanned,
    AgentReplanRequested,
    AgentSecurityAlert,
    AgentStepEvaluated,
    Event,
    EventBus,
    ToolConfirmationRequired,
    ToolExecuted,
    ToolFailed,
)


@dataclass
class AgentMetricsSummary:
    """Dataclass holding aggregated operational, planning, safety, and tool execution metrics."""

    # Planning
    plans_created: int = 0
    plans_completed: int = 0
    plans_failed: int = 0
    plans_waiting_confirmation: int = 0
    total_plan_execution_time: float = 0.0
    average_plan_execution_time: float = 0.0

    # Tasks
    tasks_executed: int = 0
    tasks_succeeded: int = 0
    tasks_failed: int = 0
    task_execution_time: float = 0.0
    average_task_execution_time: float = 0.0

    # Replanning
    replans_requested: int = 0
    replans_succeeded: int = 0
    replans_failed: int = 0
    replans_blocked_by_limit: int = 0
    replans_blocked_by_loop: int = 0

    # Security
    authorization_requests: int = 0
    confirmations_granted: int = 0
    confirmations_denied: int = 0
    unauthorized_attempts: int = 0
    invalid_tool_attempts: int = 0
    invalid_parameter_attempts: int = 0

    # Tools breakdown
    tool_errors: dict[str, int] = field(default_factory=dict)
    tool_executions: dict[str, int] = field(default_factory=dict)


class AgentMetricsCollector:
    """In-memory event subscriber computing real-time agentic operational and safety metrics."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self._lock = threading.RLock()
        self._metrics = AgentMetricsSummary()
        self._event_bus: EventBus | None = None
        if event_bus is not None:
            self.subscribe_to_bus(event_bus)

    def subscribe_to_bus(self, event_bus: EventBus) -> None:
        """Subscribes handler to EventBus events via wildcard subscription."""
        self._event_bus = event_bus
        event_bus.subscribe("*", self.handle_event)

    def handle_event(self, event: Event) -> None:
        """Processes an incoming event and updates metric counters atomically."""
        with self._lock:
            if isinstance(event, AgentPlanCreated):
                self._metrics.plans_created += 1

            elif isinstance(event, AgentPlanCompleted):
                if event.completed:
                    self._metrics.plans_completed += 1
                elif event.failed:
                    self._metrics.plans_failed += 1
                elif event.waiting_confirmation:
                    self._metrics.plans_waiting_confirmation += 1

                if event.duration_ms > 0:
                    self._metrics.total_plan_execution_time += event.duration_ms
                    completed_total = (
                        self._metrics.plans_completed
                        + self._metrics.plans_failed
                        + self._metrics.plans_waiting_confirmation
                    )
                    if completed_total > 0:
                        self._metrics.average_plan_execution_time = round(
                            self._metrics.total_plan_execution_time / completed_total, 2
                        )

            elif isinstance(event, ToolExecuted):
                self._metrics.tasks_executed += 1
                tool_name = event.tool_name or "unknown"
                self._metrics.tool_executions[tool_name] = (
                    self._metrics.tool_executions.get(tool_name, 0) + 1
                )
                if event.success:
                    self._metrics.tasks_succeeded += 1
                else:
                    self._metrics.tasks_failed += 1
                    self._metrics.tool_errors[tool_name] = (
                        self._metrics.tool_errors.get(tool_name, 0) + 1
                    )

                if event.execution_time_ms > 0:
                    self._metrics.task_execution_time += event.execution_time_ms
                    if self._metrics.tasks_executed > 0:
                        self._metrics.average_task_execution_time = round(
                            self._metrics.task_execution_time / self._metrics.tasks_executed,
                            2,
                        )

            elif isinstance(event, ToolFailed):
                tool_name = event.tool_name or "unknown"
                self._metrics.tool_errors[tool_name] = (
                    self._metrics.tool_errors.get(tool_name, 0) + 1
                )

            elif isinstance(event, AgentStepEvaluated):
                if event.evaluation_status == "FAILED":
                    self._metrics.tasks_failed += 1

            elif isinstance(event, ToolConfirmationRequired):
                self._metrics.authorization_requests += 1

            elif isinstance(event, AgentConfirmationGranted):
                self._metrics.confirmations_granted += 1

            elif isinstance(event, AgentConfirmationDenied):
                self._metrics.confirmations_denied += 1

            elif isinstance(event, AgentReplanRequested):
                self._metrics.replans_requested += 1

            elif isinstance(event, AgentReplanned):
                self._metrics.replans_succeeded += 1

            elif isinstance(event, AgentReplanFailed):
                self._metrics.replans_failed += 1
                reason_lower = event.reason.lower()
                if "limit" in reason_lower or "max_replans" in reason_lower:
                    self._metrics.replans_blocked_by_limit += 1
                if "loop" in reason_lower or "identical" in reason_lower:
                    self._metrics.replans_blocked_by_loop += 1

            elif isinstance(event, AgentSecurityAlert):
                if event.event_type == "unauthorized_attempt":
                    self._metrics.unauthorized_attempts += 1
                elif event.event_type == "invalid_tool":
                    self._metrics.invalid_tool_attempts += 1
                elif event.event_type == "invalid_parameter":
                    self._metrics.invalid_parameter_attempts += 1
                elif event.event_type == "replan_blocked_limit":
                    self._metrics.replans_blocked_by_limit += 1
                elif event.event_type == "replan_blocked_loop":
                    self._metrics.replans_blocked_by_loop += 1

    def get_summary(self) -> AgentMetricsSummary:
        """Returns a thread-safe snapshot of current aggregated metrics."""
        with self._lock:
            return AgentMetricsSummary(
                plans_created=self._metrics.plans_created,
                plans_completed=self._metrics.plans_completed,
                plans_failed=self._metrics.plans_failed,
                plans_waiting_confirmation=self._metrics.plans_waiting_confirmation,
                total_plan_execution_time=self._metrics.total_plan_execution_time,
                average_plan_execution_time=self._metrics.average_plan_execution_time,
                tasks_executed=self._metrics.tasks_executed,
                tasks_succeeded=self._metrics.tasks_succeeded,
                tasks_failed=self._metrics.tasks_failed,
                task_execution_time=self._metrics.task_execution_time,
                average_task_execution_time=self._metrics.average_task_execution_time,
                replans_requested=self._metrics.replans_requested,
                replans_succeeded=self._metrics.replans_succeeded,
                replans_failed=self._metrics.replans_failed,
                replans_blocked_by_limit=self._metrics.replans_blocked_by_limit,
                replans_blocked_by_loop=self._metrics.replans_blocked_by_loop,
                authorization_requests=self._metrics.authorization_requests,
                confirmations_granted=self._metrics.confirmations_granted,
                confirmations_denied=self._metrics.confirmations_denied,
                unauthorized_attempts=self._metrics.unauthorized_attempts,
                invalid_tool_attempts=self._metrics.invalid_tool_attempts,
                invalid_parameter_attempts=self._metrics.invalid_parameter_attempts,
                tool_errors=dict(self._metrics.tool_errors),
                tool_executions=dict(self._metrics.tool_executions),
            )
