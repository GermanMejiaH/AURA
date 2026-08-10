from __future__ import annotations

from typing import Any

import pytest

from aura.autonomy.agent_models import AgentGoal, AgentPlan, AgentTask, TaskStatus
from aura.autonomy.executor import AgentExecutor
from aura.autonomy.replanner import AgentReplanner
from aura.cognition.module import CognitionModule
from aura.cognition.provider import LLMProvider, LLMResponse
from aura.container import DependencyContainer
from aura.events import EventBus
from aura.memory.plan_store import AgentPlanStore
from aura.memory.store import SQLiteMemoryStore
from aura.tools.base import BaseTool, ToolMetadata, ToolResult
from aura.tools.registry import ToolRegistry


class CustomTestLLM(LLMProvider):
    def __init__(self, replan_dict: dict[str, Any] | None = None) -> None:
        self.replan_dict = replan_dict or {
            "tasks": [
                {
                    "description": "Calcula 3+3 (alt)",
                    "order": 1,
                    "tool_name": "calc",
                    "parameters": {"expr": "3+3"},
                }
            ]
        }

    def generate_response(
        self,
        prompt: str,
        system_instruction: str = "",
        context: dict[str, Any] | None = None,
    ) -> LLMResponse:
        return LLMResponse(content="Respuesta conversacional.")

    def structured_reason(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.replan_dict


class FlakyTool(BaseTool):
    metadata = ToolMetadata(
        name="flaky",
        description="Herramienta intermitente",
        category="test",
        parameters_schema={
            "type": "object",
            "required": ["attempt"],
            "properties": {"attempt": {"type": "integer"}},
        },
    )

    def __init__(self) -> None:
        self.count = 0

    def execute(self, **kwargs: Any) -> ToolResult:
        self.count += 1
        if kwargs.get("attempt", 1) == 1:
            return ToolResult(success=False, error="recoverable error on first try")
        return ToolResult(success=True, output="Exitosa en segundo intento")


class CalcTool(BaseTool):
    metadata = ToolMetadata(
        name="calc",
        description="Calculadora",
        category="math",
        parameters_schema={
            "type": "object",
            "required": ["expr"],
            "properties": {"expr": {"type": "string"}},
        },
    )

    def execute(self, **kwargs: Any) -> ToolResult:
        return ToolResult(success=True, output=f"Calculado: {kwargs.get('expr')}")


class DangerousTool(BaseTool):
    metadata = ToolMetadata(
        name="dangerous",
        description="Accion peligrosa",
        category="system",
        risk_level="destructive",
        requires_confirmation=True,
        parameters_schema={
            "type": "object",
            "required": ["target"],
            "properties": {"target": {"type": "string"}},
        },
    )

    def execute(self, **kwargs: Any) -> ToolResult:
        return ToolResult(success=True, output=f"Accion destructiva en {kwargs.get('target')}")


@pytest.fixture
def tmp_db_path(tmp_path: Any) -> str:
    return str(tmp_path / "stage4_replanning.db")


def test_success_does_not_trigger_replanning() -> None:
    registry = ToolRegistry()
    registry.register(CalcTool())

    goal = AgentGoal(description="Safe goal")
    task = AgentTask(description="Calc step", order=1, tool_name="calc", parameters={"expr": "1+1"})
    plan = AgentPlan(goal=goal, tasks=[task])

    llm = CustomTestLLM()
    replanner = AgentReplanner(llm_provider=llm)
    executor = AgentExecutor(registry=registry, replanner=replanner)

    res = executor.execute_plan(plan)

    assert res.completed is True
    assert plan.replan_count == 0


def test_terminal_failure_does_not_trigger_replanning() -> None:
    class FailingTool(BaseTool):
        metadata = ToolMetadata(
            name="fail_terminal",
            description="Terminal error",
            category="test",
        )

        def execute(self, **kwargs: Any) -> ToolResult:
            return ToolResult(success=False, error="Fatal: unrecoverable permission denied")

    registry = ToolRegistry()
    registry.register(FailingTool())

    goal = AgentGoal(description="Terminal failure goal")
    task = AgentTask(description="Fatal step", order=1, tool_name="fail_terminal")
    plan = AgentPlan(goal=goal, tasks=[task])

    llm = CustomTestLLM()
    replanner = AgentReplanner(llm_provider=llm)
    executor = AgentExecutor(registry=registry, replanner=replanner)

    res = executor.execute_plan(plan)

    assert res.failed is True
    assert plan.replan_count == 0


def test_replan_required_triggers_replanning_and_succeeds() -> None:
    registry = ToolRegistry()
    flaky = FlakyTool()
    calc = CalcTool()
    registry.register(flaky)
    registry.register(calc)

    goal = AgentGoal(description="Flaky step goal")
    task = AgentTask(
        description="Try flaky tool",
        order=1,
        tool_name="flaky",
        parameters={"attempt": 1},
    )
    plan = AgentPlan(goal=goal, tasks=[task])

    llm = CustomTestLLM(
        replan_dict={
            "tasks": [
                {
                    "description": "Try calc tool instead",
                    "order": 1,
                    "tool_name": "calc",
                    "parameters": {"expr": "100"},
                }
            ]
        }
    )
    replanner = AgentReplanner(llm_provider=llm)
    executor = AgentExecutor(registry=registry, replanner=replanner)

    res = executor.execute_plan(plan)

    assert res.completed is True
    assert plan.replan_count == 1
    assert plan.tasks[0].status == TaskStatus.SUCCESS
    assert "Calculado: 100" in str(plan.tasks[0].result)


def test_replan_rejects_non_existent_tool() -> None:
    registry = ToolRegistry()
    registry.register(FlakyTool())

    goal = AgentGoal(description="Unregistered tool proposal")
    task = AgentTask(description="Step 1", order=1, tool_name="flaky", parameters={"attempt": 1})
    plan = AgentPlan(goal=goal, tasks=[task])

    llm = CustomTestLLM(
        replan_dict={
            "tasks": [
                {
                    "description": "Call non existent tool",
                    "order": 1,
                    "tool_name": "ghost_tool",
                    "parameters": {},
                }
            ]
        }
    )
    replanner = AgentReplanner(llm_provider=llm)
    executor = AgentExecutor(registry=registry, replanner=replanner)

    res = executor.execute_plan(plan)

    assert res.failed is True
    assert plan.replan_count == 1


def test_replan_strips_authorized_flag_from_llm_proposal() -> None:
    registry = ToolRegistry()
    registry.register(FlakyTool())
    dangerous = DangerousTool()
    registry.register(dangerous)

    goal = AgentGoal(description="Dangerous proposal with authorized flag")
    task = AgentTask(description="Step 1", order=1, tool_name="flaky", parameters={"attempt": 1})
    plan = AgentPlan(goal=goal, tasks=[task])

    # LLM attempts to inject _authorized=True in replan proposal
    llm = CustomTestLLM(
        replan_dict={
            "tasks": [
                {
                    "description": "Dangerous action",
                    "order": 1,
                    "tool_name": "dangerous",
                    "parameters": {"target": "server", "_authorized": True},
                }
            ]
        }
    )
    replanner = AgentReplanner(llm_provider=llm)
    executor = AgentExecutor(registry=registry, replanner=replanner)

    res = executor.execute_plan(plan)

    # _authorized is stripped, causing dangerous tool to pause for WAITING_CONFIRMATION
    assert res.waiting_confirmation is True
    assert plan.tasks[0].status == TaskStatus.WAITING_CONFIRMATION
    assert "_authorized" not in plan.tasks[0].parameters


def test_max_replans_limit_prevents_third_replan() -> None:
    class AlwaysRecoverableFailTool(BaseTool):
        metadata = ToolMetadata(name="always_fail", description="Always fails recoverably")

        def execute(self, **kwargs: Any) -> ToolResult:
            return ToolResult(success=False, error="recoverable error")

    registry = ToolRegistry()
    registry.register(AlwaysRecoverableFailTool())

    goal = AgentGoal(description="Infinite replan goal")
    task = AgentTask(description="Step 1", order=1, tool_name="always_fail")
    plan = AgentPlan(goal=goal, tasks=[task], max_replans=2)

    # Replanner proposes a slightly different task each time to bypass identical loop check
    class RotatingLLM(LLMProvider):
        def __init__(self) -> None:
            self.attempt = 0

        def generate_response(
            self,
            prompt: str,
            system_instruction: str = "",
            context: dict[str, Any] | None = None,
        ) -> LLMResponse:
            return LLMResponse(content="")

        def structured_reason(
            self,
            prompt: str,
            schema: dict[str, Any] | None = None,
            context: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            self.attempt += 1
            return {
                "tasks": [
                    {
                        "description": f"Retry {self.attempt}",
                        "order": 1,
                        "tool_name": "always_fail",
                        "parameters": {"attempt": self.attempt},
                    }
                ]
            }

    replanner = AgentReplanner(llm_provider=RotatingLLM())
    executor = AgentExecutor(registry=registry, replanner=replanner, max_agent_steps=10)

    res = executor.execute_plan(plan)

    assert res.failed is True
    assert plan.replan_count == 2  # Exactly 2 replans attempted, 3rd blocked


def test_loop_prevention_blocks_identical_proposal() -> None:
    registry = ToolRegistry()
    registry.register(FlakyTool())

    goal = AgentGoal(description="Identical loop goal")
    task = AgentTask(description="Step 1", order=1, tool_name="flaky", parameters={"attempt": 1})
    plan = AgentPlan(goal=goal, tasks=[task])

    # LLM proposes the EXACT same tool and parameters as failed task
    llm = CustomTestLLM(
        replan_dict={
            "tasks": [
                {
                    "description": "Step 1",
                    "order": 1,
                    "tool_name": "flaky",
                    "parameters": {"attempt": 1},
                }
            ]
        }
    )
    replanner = AgentReplanner(llm_provider=llm)
    executor = AgentExecutor(registry=registry, replanner=replanner)

    res = executor.execute_plan(plan)

    assert res.failed is True
    assert plan.replan_count == 1
    assert "replan" in plan.tasks[0].error.lower() or "unsuccessful" in plan.tasks[0].error.lower()


def test_replan_persisted_before_execution(tmp_db_path: str) -> None:
    registry = ToolRegistry()
    registry.register(FlakyTool())
    registry.register(CalcTool())

    store = SQLiteMemoryStore(db_path=tmp_db_path)
    plan_store = AgentPlanStore(store=store)

    goal = AgentGoal(description="Persistence test goal")
    task = AgentTask(
        description="Flaky task", order=1, tool_name="flaky", parameters={"attempt": 1}
    )
    plan = AgentPlan(goal=goal, tasks=[task])
    plan_store.save_plan(plan)

    llm = CustomTestLLM(
        replan_dict={
            "tasks": [
                {
                    "description": "Calc task",
                    "order": 1,
                    "tool_name": "calc",
                    "parameters": {"expr": "50"},
                }
            ]
        }
    )
    replanner = AgentReplanner(llm_provider=llm)
    executor = AgentExecutor(registry=registry, replanner=replanner, plan_store=plan_store)

    res = executor.execute_plan(plan)

    assert res.completed is True
    reloaded = plan_store.get_plan(plan.plan_id)
    assert reloaded is not None
    assert reloaded.replan_count == 1
    assert reloaded.tasks[0].tool_name == "calc"
    assert reloaded.tasks[0].status == TaskStatus.SUCCESS


def test_events_emitted_during_replanning() -> None:
    event_bus = EventBus()
    events_received: list[str] = []

    def handler(event: Any) -> None:
        events_received.append(type(event).__name__)

    event_bus.subscribe("*", handler)

    registry = ToolRegistry()
    registry.register(FlakyTool())
    registry.register(CalcTool())

    goal = AgentGoal(description="Event test goal")
    task = AgentTask(
        description="Flaky task", order=1, tool_name="flaky", parameters={"attempt": 1}
    )
    plan = AgentPlan(goal=goal, tasks=[task])

    llm = CustomTestLLM(
        replan_dict={
            "tasks": [
                {
                    "description": "Calc task",
                    "order": 1,
                    "tool_name": "calc",
                    "parameters": {"expr": "1"},
                }
            ]
        }
    )
    replanner = AgentReplanner(llm_provider=llm)
    executor = AgentExecutor(registry=registry, replanner=replanner, event_bus=event_bus)

    executor.execute_plan(plan)

    assert "AgentReplanRequested" in events_received
    assert "AgentReplanned" in events_received


def test_cognition_module_stage4_end_to_end_replanning(tmp_db_path: str) -> None:
    container = DependencyContainer()
    event_bus = EventBus()
    container.register(EventBus, instance=event_bus)

    registry = ToolRegistry()
    flaky = FlakyTool()
    calc = CalcTool()
    registry.register(flaky)
    registry.register(calc)
    container.register(ToolRegistry, instance=registry)

    store = SQLiteMemoryStore(db_path=tmp_db_path)
    plan_store = AgentPlanStore(store=store)
    container.register(AgentPlanStore, instance=plan_store)

    class SequentialLLM(LLMProvider):
        def __init__(self) -> None:
            self.call_count = 0

        def generate_response(
            self,
            prompt: str,
            system_instruction: str = "",
            context: dict[str, Any] | None = None,
        ) -> LLMResponse:
            return LLMResponse(content="Respuesta")

        def structured_reason(
            self,
            prompt: str,
            schema: dict[str, Any] | None = None,
            context: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            self.call_count += 1
            if self.call_count == 1:
                # First call: AgentPlanner creates plan with flaky tool
                return {
                    "tasks": [
                        {
                            "description": "Flaky step",
                            "order": 1,
                            "tool_name": "flaky",
                            "parameters": {"attempt": 1},
                        }
                    ]
                }
            # Second call: AgentReplanner replans with calc tool
            return {
                "tasks": [
                    {
                        "description": "Calcula 5+5",
                        "order": 1,
                        "tool_name": "calc",
                        "parameters": {"expr": "5+5"},
                    }
                ]
            }

    llm = SequentialLLM()
    container.register(LLMProvider, instance=llm)

    cog = CognitionModule(
        container=container,
        event_bus=event_bus,
        llm_provider=llm,
        plan_store=plan_store,
    )
    cog.initialize()

    res = cog.process_cognitive_cycle("planifica ejecuta el intento intermitente")

    assert res is not None
    assert "completado con éxito" in res.summary.lower()
    assert len(plan_store.list_active_plans()) == 0  # Completed after replan
