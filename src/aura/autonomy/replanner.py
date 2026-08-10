from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from ..cognition.evaluator import EvaluationResult
from ..cognition.provider import LLMProvider
from ..events import AgentSecurityAlert, EventBus
from ..logging import get_logger
from .agent_models import AgentPlan, AgentTask, TaskStatus
from .observation import Observation

if TYPE_CHECKING:
    from ..tools.registry import ToolRegistry


class AgentReplanner:
    """Generates and validates alternative plan strategies when a task execution fails."""

    def __init__(
        self,
        llm_provider: LLMProvider | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.llm_provider = llm_provider
        self.event_bus = event_bus

    def replan(
        self,
        plan: AgentPlan,
        failed_task: AgentTask,
        observation: Observation,
        eval_result: EvaluationResult,
        registry: ToolRegistry | None = None,
    ) -> bool:
        """Attempts to generate and validate a revised set of tasks for a plan."""
        logger = get_logger("AgentReplanner")

        if plan.replan_count >= plan.max_replans:
            logger.warning(
                f"Re-planning limit reached ({plan.replan_count}/{plan.max_replans}) "
                f"for plan '{plan.plan_id}'."
            )
            if self.event_bus is not None:
                self.event_bus.publish(
                    AgentSecurityAlert(
                        source="AgentReplanner",
                        event_type="replan_blocked_limit",
                        tool_name=failed_task.tool_name or "",
                        reason="Re-planning limit reached",
                        plan_id=plan.plan_id,
                        task_id=failed_task.task_id,
                    )
                )
            return False

        plan.replan_count += 1
        logger.info(
            f"Attempting replan #{plan.replan_count}/{plan.max_replans} for task "
            f"'{failed_task.task_id}' in plan '{plan.plan_id}'."
        )

        proposal_data: dict[str, Any] | None = None

        if self.llm_provider is not None:
            prompt = self._build_replan_prompt(
                plan, failed_task, observation, eval_result, registry
            )
            schema = {
                "type": "object",
                "required": ["tasks"],
                "properties": {
                    "tasks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["description", "tool_name", "parameters"],
                            "properties": {
                                "description": {"type": "string"},
                                "tool_name": {"type": "string"},
                                "parameters": {"type": "object"},
                            },
                        },
                    }
                },
            }
            try:
                proposal_data = self.llm_provider.structured_reason(prompt, schema=schema)
            except Exception as exc:
                logger.warning(f"LLM structured_reason failed during replan: {exc}")

        if not proposal_data or not isinstance(proposal_data.get("tasks"), list):
            logger.warning("Replanning proposal is missing or invalid.")
            return False

        proposed_task_dicts: list[dict[str, Any]] = proposal_data["tasks"]
        if not proposed_task_dicts:
            logger.warning("Replanning proposal contains empty tasks array.")
            return False

        # Validate proposed tasks deterministically
        validated_tasks: list[AgentTask] = []
        base_order = failed_task.order

        for idx, task_dict in enumerate(proposed_task_dicts, start=1):
            tool_name = task_dict.get("tool_name")
            desc = task_dict.get("description", f"Replanned step {idx}")
            raw_params = task_dict.get("parameters", {})

            if not isinstance(raw_params, dict):
                raw_params = {}

            # Security: Purge any LLM-injected authorization flags
            if "_authorized" in raw_params:
                raw_params.pop("_authorized", None)
                if self.event_bus is not None:
                    self.event_bus.publish(
                        AgentSecurityAlert(
                            source="AgentReplanner",
                            event_type="unauthorized_attempt",
                            tool_name=tool_name or "",
                            reason="Stripped _authorized parameter from LLM proposal",
                            plan_id=plan.plan_id,
                            task_id=failed_task.task_id,
                        )
                    )

            if tool_name and registry is not None:
                tool = registry.get(tool_name)
                if tool is None:
                    logger.warning(f"Replanned task proposes unregistered tool '{tool_name}'.")
                    if self.event_bus is not None:
                        self.event_bus.publish(
                            AgentSecurityAlert(
                                source="AgentReplanner",
                                event_type="invalid_tool",
                                tool_name=tool_name,
                                reason=f"Tool '{tool_name}' not registered",
                                plan_id=plan.plan_id,
                                task_id=failed_task.task_id,
                            )
                        )
                    return False

            # Infinite loop prevention: check if identical to failed task
            if tool_name == failed_task.tool_name and json.dumps(
                raw_params, sort_keys=True
            ) == json.dumps(failed_task.parameters, sort_keys=True):
                logger.warning(
                    f"Replanning proposal for tool '{tool_name}' is identical to the failed "
                    "task. Aborting to prevent infinite loop."
                )
                if self.event_bus is not None:
                    self.event_bus.publish(
                        AgentSecurityAlert(
                            source="AgentReplanner",
                            event_type="replan_blocked_loop",
                            tool_name=tool_name or "",
                            reason="Identical proposal rejected to prevent infinite loop",
                            plan_id=plan.plan_id,
                            task_id=failed_task.task_id,
                        )
                    )
                return False

            new_task = AgentTask(
                description=desc,
                order=base_order + idx - 1,
                status=TaskStatus.PENDING,
                tool_name=tool_name,
                parameters=raw_params,
            )
            validated_tasks.append(new_task)

        # Truncate/replace failed task and subsequent PENDING tasks
        updated_tasks: list[AgentTask] = []
        for t in plan.get_ordered_tasks():
            if t.task_id == failed_task.task_id or t.status == TaskStatus.PENDING:
                continue
            updated_tasks.append(t)

        updated_tasks.extend(validated_tasks)
        plan.tasks = updated_tasks

        logger.info(
            f"Successfully replanned plan '{plan.plan_id}' with {len(validated_tasks)} new tasks."
        )
        return True

    def _build_replan_prompt(
        self,
        plan: AgentPlan,
        failed_task: AgentTask,
        observation: Observation,
        eval_result: EvaluationResult,
        registry: ToolRegistry | None,
    ) -> str:
        tools_desc = ""
        if registry is not None:
            available_tools = registry.list_metadata()
            tools_desc = "\nAvailable Tools:\n" + "\n".join(
                f"- {t.name}: {t.description}" for t in available_tools
            )

        return (
            f"Goal: {plan.goal.description}\n"
            f"Failed Task: {failed_task.description} (Tool: {failed_task.tool_name})\n"
            f"Parameters: {json.dumps(failed_task.parameters)}\n"
            f"Error/Observation: {observation.error or eval_result.reason}\n"
            f"{tools_desc}\n\n"
            "Propose a alternative sequence of valid tasks to overcome this error "
            "and achieve the goal."
        )
