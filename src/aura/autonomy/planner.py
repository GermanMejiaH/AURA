from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from ..cognition.deliberation import (
    DeliberationEngine,
    GoalModel,
    OutcomeSimulator,
    StrategySelection,
    StrategySelector,
)
from ..events import (
    AgentPlanCreated,
    AgentSecurityAlert,
    EventBus,
    StrategyDeliberated,
    StrategySelected,
)
from ..logging import get_logger
from .agent_models import AgentGoal, AgentPlan, AgentTask, TaskStatus

if TYPE_CHECKING:
    from ..cognition.provider import LLMProvider
    from ..tools.registry import ToolRegistry


class AgentPlanner:
    """Generates structured AgentPlan domain models from high-level goals.

    Uses deliberation pipeline or LLM inference.
    """

    DEFAULT_MAX_PLAN_STEPS: int = 5

    def __init__(
        self,
        llm_provider: LLMProvider | None = None,
        registry: ToolRegistry | None = None,
        max_plan_steps: int = DEFAULT_MAX_PLAN_STEPS,
        event_bus: EventBus | None = None,
        deliberator: DeliberationEngine | None = None,
        simulator: OutcomeSimulator | None = None,
        selector: StrategySelector | None = None,
    ) -> None:
        self.llm_provider = llm_provider
        self.registry = registry
        self.max_plan_steps = max_plan_steps
        self.event_bus = event_bus
        self.deliberator = deliberator
        self.simulator = simulator
        self.selector = selector

    def _ensure_goal_model(self, goal: AgentGoal | GoalModel | str) -> GoalModel:
        """Converts an AgentGoal or string safely into a GoalModel."""
        if isinstance(goal, GoalModel):
            return goal
        elif isinstance(goal, AgentGoal):
            return GoalModel(
                description=goal.description,
                goal_id=goal.goal_id,
                status=goal.status,
            )
        else:
            return GoalModel(description=str(goal))

    def plan_from_strategy(
        self,
        goal: AgentGoal | GoalModel,
        selection: StrategySelection,
    ) -> AgentPlan:
        """Converts a chosen StrategySelection into an executable AgentPlan."""
        target_goal = goal if isinstance(goal, AgentGoal) else AgentGoal(description=str(goal))
        strategy = selection.chosen_strategy
        tasks: list[AgentTask] = []

        tools = list(strategy.required_tools)
        for idx, step_desc in enumerate(strategy.steps_outline, start=1):
            tool_name = tools[idx - 1] if idx - 1 < len(tools) else None
            tasks.append(
                AgentTask(
                    description=step_desc,
                    order=idx,
                    tool_name=tool_name,
                    parameters={},
                    status=TaskStatus.PENDING,
                )
            )

        plan = AgentPlan(
            goal=target_goal,
            tasks=tasks,
            strategy_id=strategy.strategy_id,
            strategy_name=strategy.name,
        )

        if self.event_bus is not None:
            self.event_bus.publish(
                AgentPlanCreated(
                    source="AgentPlanner",
                    plan_id=plan.plan_id,
                    goal_description=plan.goal.description,
                    tasks_count=len(plan.tasks),
                )
            )

        return plan

    def deliberate_and_plan(
        self,
        goal: AgentGoal | GoalModel | str,
    ) -> tuple[StrategySelection, AgentPlan]:
        """Runs full E2E deliberation (DELIBERATE -> SIMULATE -> SELECT -> PLAN)."""
        goal_model = self._ensure_goal_model(goal)
        tools = [meta.name for meta in self.registry.list_metadata()] if self.registry else []

        deliberator = self.deliberator or DeliberationEngine()
        candidates = deliberator.deliberate(goal_model, available_tools=tools)

        if self.event_bus is not None:
            self.event_bus.publish(
                StrategyDeliberated(
                    source="AgentPlanner",
                    goal_id=goal_model.goal_id,
                    candidates_count=len(candidates),
                )
            )

        if self.simulator is None:
            from ..memory.retrieval import MemoryRetriever

            simulator = OutcomeSimulator(MemoryRetriever())
        else:
            simulator = self.simulator

        simulations = [simulator.simulate(c, goal_model) for c in candidates]

        selector = self.selector or StrategySelector()
        selection = selector.select(goal_model, candidates, simulations)

        if self.event_bus is not None:
            self.event_bus.publish(
                StrategySelected(
                    source="AgentPlanner",
                    goal_id=goal_model.goal_id,
                    strategy_id=selection.chosen_strategy.strategy_id,
                    strategy_name=selection.chosen_strategy.name,
                )
            )

        plan = self.plan_from_strategy(goal_model, selection)
        return selection, plan

    def create_plan(
        self,
        goal: AgentGoal | GoalModel | str,
        context: dict[str, Any] | None = None,
    ) -> AgentPlan:
        """Translates a natural language goal into a validated AgentPlan."""
        logger = get_logger("AgentPlanner")

        if (
            self.deliberator is not None
            or self.simulator is not None
            or self.selector is not None
            or isinstance(goal, GoalModel)
        ):
            _, plan = self.deliberate_and_plan(goal)
            return plan

        if isinstance(goal, str):
            target_goal = AgentGoal(description=goal)
        else:
            target_goal = goal

        if self.llm_provider is None:
            raise ValueError("LLMProvider is required for AgentPlanner to generate plans")

        # 1. Build structured tools metadata context
        tools_info: list[dict[str, Any]] = []
        if self.registry is not None:
            for meta in self.registry.list_metadata():
                tools_info.append(
                    {
                        "name": meta.name,
                        "description": meta.description,
                        "category": meta.category,
                        "parameters_schema": meta.parameters_schema,
                        "requires_confirmation": meta.requires_confirmation,
                        "risk_level": meta.risk_level,
                    }
                )

        # 2. Build prompt for LLM
        prompt = (
            f"Goal: {target_goal.description}\n"
            f"Available Tools: {json.dumps(tools_info, indent=2)}\n"
            f"Max Plan Steps Allowed: {self.max_plan_steps}\n\n"
            "Generate a multi-step plan to achieve the goal using the available tools.\n"
            "Respond ONLY with a JSON object with this structure:\n"
            "{\n"
            '  "tasks": [\n'
            "    {\n"
            '      "description": "Task step description",\n'
            '      "order": 1,\n'
            '      "tool_name": "tool_name_or_null",\n'
            '      "parameters": {"param1": "val1"}\n'
            "    }\n"
            "  ]\n"
            "}\n"
        )

        system_instruction = (
            "You are AURA's Autonomous Agent Planner.\n"
            "RULES:\n"
            "1. Output ONLY valid JSON, no markdown wrappers, no commentary.\n"
            "2. Never use tools that are not in Available Tools.\n"
            "3. Ensure all tool parameters strictly match the tool's parameters_schema.\n"
            "4. Do NOT include parameter '_authorized'.\n"
            "5. Respect Max Plan Steps Allowed.\n"
        )

        # 3. Call LLM
        llm_context: dict[str, Any] = {"tools": tools_info, "max_steps": self.max_plan_steps}
        if context:
            llm_context.update(context)

        raw_json_dict: dict[str, Any] | None = None

        try:
            structured_res = self.llm_provider.structured_reason(
                prompt=prompt,
                schema={"type": "object", "properties": {"tasks": {"type": "array"}}},
                context=llm_context,
            )
            if isinstance(structured_res, dict) and "tasks" in structured_res:
                raw_json_dict = structured_res
        except Exception as exc:
            logger.warning(f"structured_reason failed: {exc}. Trying generate_response fallback.")

        if raw_json_dict is None:
            llm_res = self.llm_provider.generate_response(
                prompt=prompt,
                system_instruction=system_instruction,
                context=llm_context,
            )
            raw_json_dict = self._parse_json_response(llm_res.content)

        # 4. Deterministic Validation
        tasks_raw = raw_json_dict.get("tasks")
        if not isinstance(tasks_raw, list) or not tasks_raw:
            raise ValueError(f"AgentPlanner received no tasks for goal '{target_goal.description}'")

        if len(tasks_raw) > self.max_plan_steps:
            msg = (
                f"AgentPlan task count ({len(tasks_raw)}) "
                f"exceeds maximum limit of {self.max_plan_steps}"
            )
            raise ValueError(msg)

        seen_task_ids: set[str] = set()
        created_tasks: list[AgentTask] = []

        for idx, task_item in enumerate(tasks_raw, start=1):
            if not isinstance(task_item, dict):
                raise TypeError(f"Task at index {idx} is not a valid dictionary")

            task_desc = task_item.get("description")
            if not task_desc or not isinstance(task_desc, str):
                raise ValueError(f"Task at index {idx} missing valid 'description'")

            order_val = task_item.get("order", idx)
            if not isinstance(order_val, int):
                try:
                    order_val = int(order_val)
                except ValueError, TypeError:
                    order_val = idx

            tool_name = task_item.get("tool_name")
            if tool_name is not None and not isinstance(tool_name, str):
                raise ValueError(f"Task '{task_desc}' has non-string tool_name")

            if tool_name == "" or tool_name == "null":
                tool_name = None

            parameters = task_item.get("parameters", {})
            if not isinstance(parameters, dict):
                raise TypeError(f"Task '{task_desc}' parameters must be a dictionary")

            # Security Enforcement: Strip any '_authorized' parameter injected by LLM
            if "_authorized" in parameters:
                parameters.pop("_authorized", None)
                if self.event_bus is not None:
                    self.event_bus.publish(
                        AgentSecurityAlert(
                            source="AgentPlanner",
                            event_type="unauthorized_attempt",
                            tool_name=tool_name or "",
                            reason="Stripped _authorized parameter from LLM proposal",
                        )
                    )

            # Tool and parameter schema validation against ToolRegistry
            if tool_name:
                if self.registry is None:
                    msg = (
                        f"ToolRegistry is required to validate tool '{tool_name}' "
                        f"in task '{task_desc}'"
                    )
                    raise ValueError(msg)

                tool_obj = self.registry.get(tool_name)
                if tool_obj is None:
                    if self.event_bus is not None:
                        self.event_bus.publish(
                            AgentSecurityAlert(
                                source="AgentPlanner",
                                event_type="invalid_tool",
                                tool_name=tool_name,
                                reason=f"Tool '{tool_name}' not registered",
                            )
                        )
                    msg = (
                        f"Tool '{tool_name}' specified in task '{task_desc}' "
                        "is not registered in ToolRegistry"
                    )
                    raise ValueError(msg)

                valid, val_err = self.registry.validate_parameters(tool_name, **parameters)
                if not valid:
                    if self.event_bus is not None:
                        self.event_bus.publish(
                            AgentSecurityAlert(
                                source="AgentPlanner",
                                event_type="invalid_parameter",
                                tool_name=tool_name,
                                reason=val_err or "Invalid parameters schema",
                            )
                        )
                    msg = (
                        f"Invalid parameters for tool '{tool_name}' "
                        f"in task '{task_desc}': {val_err}"
                    )
                    raise ValueError(msg)

            custom_task_id = task_item.get("task_id")
            if custom_task_id and isinstance(custom_task_id, str):
                if custom_task_id in seen_task_ids:
                    raise ValueError(f"Duplicate task_id '{custom_task_id}' detected in plan")
                seen_task_ids.add(custom_task_id)
                task_obj = AgentTask(
                    description=task_desc,
                    order=order_val,
                    task_id=custom_task_id,
                    tool_name=tool_name,
                    parameters=parameters,
                    status=TaskStatus.PENDING,
                )
            else:
                task_obj = AgentTask(
                    description=task_desc,
                    order=order_val,
                    tool_name=tool_name,
                    parameters=parameters,
                    status=TaskStatus.PENDING,
                )

            created_tasks.append(task_obj)

        plan = AgentPlan(goal=target_goal, tasks=created_tasks)
        logger.info(f"AgentPlan successfully created with {len(plan.tasks)} tasks.")

        if self.event_bus is not None:
            self.event_bus.publish(
                AgentPlanCreated(
                    source="AgentPlanner",
                    plan_id=plan.plan_id,
                    goal_description=plan.goal.description,
                    tasks_count=len(plan.tasks),
                )
            )

        return plan

    @staticmethod
    def _parse_json_response(content: str) -> dict[str, Any]:
        """Extracts and parses JSON dictionary from LLM response text cleanly."""
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"\s*```$", "", cleaned)
            cleaned = cleaned.strip()

        json_match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
        if json_match:
            cleaned = json_match.group(1)

        try:
            data = json.loads(cleaned)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError as exc:
            msg = f"Failed to parse LLM response as JSON: {exc}. Content: {content[:100]}"
            raise ValueError(msg) from exc

        msg = f"Parsed JSON response is not a dictionary. Content: {content[:100]}"
        raise ValueError(msg)
