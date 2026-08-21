"""Stage 19 — Real Capability Vertical Slice Runner.

Provides a unified end-to-end operational turn runner linking:
User Input -> Intent -> Goal -> ToolRegistry -> Stage 16 Orchestrator -> Response
without introducing new executive authorities or violating Stage 10-16 boundaries.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from aura.cognition.goals import GoalManager, PersistentGoal
from aura.cognition.intent import Intent, IntentDetector
from aura.events import EventBus
from aura.logging import get_logger
from aura.tools.base import ToolResult
from aura.tools.registry import ToolRegistry

from .orchestration import RuntimeOperation, RuntimeOperationState, RuntimeOrchestrator

logger = get_logger("RealCapabilityVerticalSlice")


@dataclass(frozen=True)
class VerticalSliceResult:
    """Immutable result emitted by RealCapabilityVerticalSlice processing turn."""

    user_input: str
    intent: Intent
    goal_id: str
    action_id: str
    operation_id: str
    correlation_id: str
    execution_id: str | None
    outcome_id: str | None
    adaptation_proposal_id: str | None
    output: Any
    success: bool
    error: str | None
    operation: RuntimeOperation


class RealCapabilityVerticalSlice:
    """End-to-end runner linking conversational turn input to Stage 16 closed-loop execution."""

    def __init__(
        self,
        orchestrator: RuntimeOrchestrator | None = None,
        tool_registry: ToolRegistry | None = None,
        goal_manager: GoalManager | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.orchestrator = orchestrator or RuntimeOrchestrator(event_bus=event_bus)
        self.tool_registry = tool_registry or ToolRegistry()
        self.goal_manager = goal_manager or GoalManager(event_bus=event_bus)
        self.event_bus = event_bus

    def process_turn(
        self,
        user_input: str,
        correlation_id: str | None = None,
        target_tool_name: str | None = None,
        tool_kwargs: dict[str, Any] | None = None,
        action_fn: Callable[[], Any] | None = None,
    ) -> VerticalSliceResult:
        """Processes a real user turn through intent, goal creation, and Stage 16 execution."""
        # 1. Detect Intent
        intent = IntentDetector.detect(user_input)
        logger.info(f"Processing turn for input '{user_input}' (intent={intent.intent_type.value})")

        # 2. Create Goal
        goal_desc = f"Process input turn: {user_input[:50]}"
        persistent_goal: PersistentGoal = self.goal_manager.create_goal(description=goal_desc)
        goal_id = persistent_goal.goal_id

        # 3. Resolve Tool / Action
        action_id = target_tool_name or "datetime_tool"
        kwargs = tool_kwargs or {}

        # Construct execution function if not supplied
        if action_fn is None:
            tool = self.tool_registry.get(action_id)
            if tool is not None:

                def _real_action() -> Any:
                    tool_res: ToolResult = tool.execute(**kwargs)
                    if not tool_res.success:
                        raise RuntimeError(tool_res.error or f"Tool '{action_id}' execution failed")
                    return tool_res.output

                exec_fn: Callable[[], Any] = _real_action
            else:

                def _default_action() -> Any:
                    return f"Executed turn for intent '{intent.intent_type.value}'"

                exec_fn = _default_action
        else:
            exec_fn = action_fn

        # 4. Execute closed-loop via Stage 16 RuntimeOrchestrator
        operation = self.orchestrator.execute_closed_loop(
            action_id=action_id,
            goal_id=goal_id,
            correlation_id=correlation_id,
            action_fn=exec_fn,
            metadata={
                "user_input": user_input,
                "intent_type": intent.intent_type.value,
                "tool_name": action_id,
            },
        )

        success = operation.state == RuntimeOperationState.COMPLETED
        err_msg = operation.failure_reason if not success else None
        output = None
        if success and self.orchestrator.execution_engine:
            # Output stored in operation execution context or execution result
            output = operation.metadata.get("output", f"Turn completed for '{action_id}'")

        return VerticalSliceResult(
            user_input=user_input,
            intent=intent,
            goal_id=goal_id,
            action_id=action_id,
            operation_id=operation.operation_id,
            correlation_id=operation.correlation_id,
            execution_id=operation.execution_id,
            outcome_id=operation.outcome_id,
            adaptation_proposal_id=operation.adaptation_proposal_id,
            output=output,
            success=success,
            error=err_msg,
            operation=operation,
        )
