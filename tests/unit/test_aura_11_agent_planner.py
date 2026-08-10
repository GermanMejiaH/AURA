from __future__ import annotations

from typing import Any

import pytest

from aura.autonomy.agent_models import AgentGoal, AgentPlan, TaskStatus
from aura.autonomy.planner import AgentPlanner
from aura.cognition.provider import LLMProvider, LLMResponse
from aura.tools.base import BaseTool, ToolMetadata, ToolResult
from aura.tools.registry import ToolRegistry


class SampleCalculatorTool(BaseTool):
    metadata = ToolMetadata(
        name="calculator",
        description="Calculates basic arithmetic expressions",
        category="math",
        parameters_schema={
            "type": "object",
            "required": ["expression"],
            "properties": {"expression": {"type": "string"}},
        },
    )

    def __init__(self) -> None:
        self.executed_count = 0

    def execute(self, **kwargs: Any) -> ToolResult:
        self.executed_count += 1
        return ToolResult(success=True, output="42")


class CustomStructuredMockLLM(LLMProvider):
    """Custom Mock LLM Provider to return specific structured outputs for unit tests."""

    def __init__(
        self,
        response_dict: dict[str, Any] | None = None,
        raw_text: str | None = None,
    ) -> None:
        self.response_dict = response_dict or {}
        self.raw_text = raw_text
        self.generate_called = False
        self.structured_called = False

    def generate_response(
        self,
        prompt: str,
        system_instruction: str = "",
        context: dict[str, Any] | None = None,
    ) -> LLMResponse:
        self.generate_called = True
        return LLMResponse(content=self.raw_text or "{}")

    def structured_reason(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.structured_called = True
        if self.response_dict is not None:
            return self.response_dict
        raise ValueError("Simulated structured_reason error")


def create_test_registry() -> tuple[ToolRegistry, SampleCalculatorTool]:
    registry = ToolRegistry()
    calc_tool = SampleCalculatorTool()
    registry.register(calc_tool)
    return registry, calc_tool


def test_agent_planner_missing_llm_provider() -> None:
    planner = AgentPlanner(llm_provider=None)
    with pytest.raises(ValueError, match="LLMProvider is required"):
        planner.create_plan("Calculate 2+2")


def test_agent_planner_successful_plan_generation() -> None:
    registry, calc_tool = create_test_registry()
    llm = CustomStructuredMockLLM(
        response_dict={
            "tasks": [
                {
                    "description": "Calculate 2+2",
                    "order": 1,
                    "tool_name": "calculator",
                    "parameters": {"expression": "2+2"},
                }
            ]
        }
    )

    planner = AgentPlanner(llm_provider=llm, registry=registry)
    plan = planner.create_plan("Calculate 2+2")

    assert isinstance(plan, AgentPlan)
    assert plan.goal.description == "Calculate 2+2"
    assert len(plan.tasks) == 1
    task = plan.tasks[0]
    assert task.description == "Calculate 2+2"
    assert task.order == 1
    assert task.tool_name == "calculator"
    assert task.parameters == {"expression": "2+2"}
    assert task.status == TaskStatus.PENDING
    # Ensure tool was NOT executed during planning
    assert calc_tool.executed_count == 0


def test_agent_planner_accepts_agent_goal_object() -> None:
    registry, _ = create_test_registry()
    llm = CustomStructuredMockLLM(
        response_dict={
            "tasks": [
                {
                    "description": "Calculate 5*5",
                    "order": 1,
                    "tool_name": "calculator",
                    "parameters": {"expression": "5*5"},
                }
            ]
        }
    )
    goal = AgentGoal(description="Calculate 5*5")

    planner = AgentPlanner(llm_provider=llm, registry=registry)
    plan = planner.create_plan(goal)

    assert plan.goal == goal
    assert len(plan.tasks) == 1


def test_agent_planner_strips_authorized_parameter() -> None:
    registry, _ = create_test_registry()
    llm = CustomStructuredMockLLM(
        response_dict={
            "tasks": [
                {
                    "description": "Bypass safety test",
                    "order": 1,
                    "tool_name": "calculator",
                    "parameters": {"expression": "10/2", "_authorized": True},
                }
            ]
        }
    )

    planner = AgentPlanner(llm_provider=llm, registry=registry)
    plan = planner.create_plan("Bypass test")

    assert "_authorized" not in plan.tasks[0].parameters


def test_agent_planner_unknown_tool_rejection() -> None:
    registry, _ = create_test_registry()
    llm = CustomStructuredMockLLM(
        response_dict={
            "tasks": [
                {
                    "description": "Run unknown tool",
                    "order": 1,
                    "tool_name": "non_existent_tool",
                    "parameters": {},
                }
            ]
        }
    )

    planner = AgentPlanner(llm_provider=llm, registry=registry)
    with pytest.raises(ValueError, match="not registered in ToolRegistry"):
        planner.create_plan("Run unknown tool")


def test_agent_planner_invalid_parameters_rejection() -> None:
    registry, _ = create_test_registry()
    # Missing required parameter 'expression'
    llm = CustomStructuredMockLLM(
        response_dict={
            "tasks": [
                {
                    "description": "Calculate without expression",
                    "order": 1,
                    "tool_name": "calculator",
                    "parameters": {},
                }
            ]
        }
    )

    planner = AgentPlanner(llm_provider=llm, registry=registry)
    with pytest.raises(ValueError, match="Invalid parameters for tool 'calculator'"):
        planner.create_plan("Invalid params test")


def test_agent_planner_empty_tasks_rejection() -> None:
    registry, _ = create_test_registry()
    llm = CustomStructuredMockLLM(response_dict={"tasks": []})

    planner = AgentPlanner(llm_provider=llm, registry=registry)
    with pytest.raises(ValueError, match="received no tasks"):
        planner.create_plan("Empty plan test")


def test_agent_planner_exceeds_max_plan_steps() -> None:
    registry, _ = create_test_registry()
    tasks_list = [
        {
            "description": f"Step {i}",
            "order": i,
            "tool_name": "calculator",
            "parameters": {"expression": f"{i}+{i}"},
        }
        for i in range(1, 7)
    ]
    llm = CustomStructuredMockLLM(response_dict={"tasks": tasks_list})

    planner = AgentPlanner(llm_provider=llm, registry=registry, max_plan_steps=5)
    with pytest.raises(ValueError, match="exceeds maximum limit of 5"):
        planner.create_plan("Exceed max steps")


def test_agent_planner_duplicate_task_ids() -> None:
    registry, _ = create_test_registry()
    llm = CustomStructuredMockLLM(
        response_dict={
            "tasks": [
                {
                    "task_id": "duplicate_id",
                    "description": "Step 1",
                    "order": 1,
                    "tool_name": "calculator",
                    "parameters": {"expression": "1+1"},
                },
                {
                    "task_id": "duplicate_id",
                    "description": "Step 2",
                    "order": 2,
                    "tool_name": "calculator",
                    "parameters": {"expression": "2+2"},
                },
            ]
        }
    )

    planner = AgentPlanner(llm_provider=llm, registry=registry)
    with pytest.raises(ValueError, match="Duplicate task_id 'duplicate_id'"):
        planner.create_plan("Duplicate task IDs")


def test_agent_planner_malformed_json_fallback() -> None:
    registry, _ = create_test_registry()
    # structured_reason fails, generate_response returns valid JSON string inside markdown
    json_markdown = (
        "```json\n"
        "{\n"
        '  "tasks": [\n'
        "    {\n"
        '      "description": "Step 1",\n'
        '      "order": 1,\n'
        '      "tool_name": "calculator",\n'
        '      "parameters": {"expression": "3*3"}\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "```"
    )
    llm = CustomStructuredMockLLM(
        response_dict=None,
        raw_text=json_markdown,
    )

    planner = AgentPlanner(llm_provider=llm, registry=registry)
    plan = planner.create_plan("Markdown JSON test")

    assert len(plan.tasks) == 1
    assert plan.tasks[0].parameters == {"expression": "3*3"}


def test_agent_planner_unparseable_llm_response() -> None:
    registry, _ = create_test_registry()
    llm = CustomStructuredMockLLM(response_dict=None, raw_text="This is plain text with no JSON.")

    planner = AgentPlanner(llm_provider=llm, registry=registry)
    with pytest.raises(ValueError, match="Failed to parse LLM response as JSON"):
        planner.create_plan("Unparseable test")


def test_agent_planner_never_executes_tools() -> None:
    registry, calc_tool = create_test_registry()
    llm = CustomStructuredMockLLM(
        response_dict={
            "tasks": [
                {
                    "description": "Step 1",
                    "order": 1,
                    "tool_name": "calculator",
                    "parameters": {"expression": "100+100"},
                },
                {
                    "description": "Step 2",
                    "order": 2,
                    "tool_name": "calculator",
                    "parameters": {"expression": "200+200"},
                },
            ]
        }
    )

    planner = AgentPlanner(llm_provider=llm, registry=registry)
    plan = planner.create_plan("No execution test")

    assert len(plan.tasks) == 2
    assert all(t.status == TaskStatus.PENDING for t in plan.tasks)
    assert calc_tool.executed_count == 0
