from __future__ import annotations

from typing import Any

import pytest

from aura.autonomy.agent_models import TaskStatus
from aura.cognition.module import CognitionModule
from aura.cognition.provider import LLMProvider, LLMResponse
from aura.container import DependencyContainer
from aura.events import EventBus
from aura.memory.plan_store import AgentPlanStore
from aura.memory.store import SQLiteMemoryStore
from aura.tools.base import BaseTool, ToolMetadata, ToolResult
from aura.tools.registry import ToolRegistry


class CustomTestLLM(LLMProvider):
    def __init__(self, response_dict: dict[str, Any] | None = None) -> None:
        self.response_dict = response_dict or {
            "tasks": [
                {
                    "description": "Calcula 2+2",
                    "order": 1,
                    "tool_name": "calc",
                    "parameters": {"expr": "2+2"},
                }
            ]
        }
        self.generate_called = False

    def generate_response(
        self,
        prompt: str,
        system_instruction: str = "",
        context: dict[str, Any] | None = None,
    ) -> LLMResponse:
        self.generate_called = True
        return LLMResponse(content="Respuesta conversacional por defecto.")

    def structured_reason(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.response_dict


class CalcTool(BaseTool):
    metadata = ToolMetadata(
        name="calc",
        description="Calculadora basica",
        category="math",
        parameters_schema={
            "type": "object",
            "required": ["expr"],
            "properties": {"expr": {"type": "string"}},
        },
    )

    def __init__(self) -> None:
        self.count = 0

    def execute(self, **kwargs: Any) -> ToolResult:
        self.count += 1
        return ToolResult(success=True, output=f"Resultado: {kwargs.get('expr')}")


class DangerousTool(BaseTool):
    metadata = ToolMetadata(
        name="dangerous",
        description="Accion peligrosa",
        category="system",
        risk_level="destructive",
        requires_confirmation=True,
        parameters_schema={
            "type": "object",
            "required": ["cmd"],
            "properties": {"cmd": {"type": "string"}},
        },
    )

    def __init__(self) -> None:
        self.count = 0

    def execute(self, **kwargs: Any) -> ToolResult:
        self.count += 1
        return ToolResult(success=True, output=f"Accion destructiva ejecutada: {kwargs.get('cmd')}")


@pytest.fixture
def tmp_db_path(tmp_path: Any) -> str:
    return str(tmp_path / "stage3_aura.db")


type CogSetupReturn = tuple[
    CognitionModule,
    DependencyContainer,
    ToolRegistry,
    AgentPlanStore,
    CalcTool,
    DangerousTool,
]


def setup_cognition_environment(
    db_path: str,
    llm: LLMProvider | None = None,
) -> CogSetupReturn:
    container = DependencyContainer()
    event_bus = EventBus()
    container.register(EventBus, instance=event_bus)

    registry = ToolRegistry()
    calc = CalcTool()
    dangerous = DangerousTool()
    registry.register(calc)
    registry.register(dangerous)
    container.register(ToolRegistry, instance=registry)

    store = SQLiteMemoryStore(db_path=db_path)
    plan_store = AgentPlanStore(store=store)
    container.register(AgentPlanStore, instance=plan_store)

    test_llm = llm or CustomTestLLM()
    container.register(LLMProvider, instance=test_llm)

    cog = CognitionModule(
        container=container,
        event_bus=event_bus,
        llm_provider=test_llm,
        plan_store=plan_store,
    )
    cog.initialize()

    return cog, container, registry, plan_store, calc, dangerous


def test_agentic_request_creates_persists_and_executes_plan(tmp_db_path: str) -> None:
    cog, _, _, plan_store, calc, _ = setup_cognition_environment(tmp_db_path)

    res = cog.process_cognitive_cycle("planifica organiza y calcula 2+2")

    assert res is not None
    assert "Plan completado con éxito" in res.summary
    assert calc.count == 1

    active = plan_store.list_active_plans()
    assert len(active) == 0  # Completed plan is not active

    # Get plan directly from DB
    cursor = plan_store.store._get_connection().execute("SELECT plan_id FROM agent_plans")
    plan_id = cursor.fetchone()["plan_id"]
    saved_plan = plan_store.get_plan(plan_id)

    assert saved_plan is not None
    assert saved_plan.is_completed() is True
    assert saved_plan.tasks[0].status == TaskStatus.SUCCESS


def test_dangerous_tool_triggers_waiting_confirmation_and_persists(tmp_db_path: str) -> None:
    llm = CustomTestLLM(
        response_dict={
            "tasks": [
                {
                    "description": "Ejecutar comando peligroso",
                    "order": 1,
                    "tool_name": "dangerous",
                    "parameters": {"cmd": "rm -rf /"},
                }
            ]
        }
    )
    cog, _, _, plan_store, _, dangerous = setup_cognition_environment(tmp_db_path, llm=llm)

    res = cog.process_cognitive_cycle("planifica ejecuta el comando peligroso")

    assert "necesito tu confirmación" in res.summary
    assert dangerous.count == 0

    active = plan_store.list_active_plans()
    assert len(active) == 1
    assert active[0].is_waiting_confirmation() is True
    assert active[0].tasks[0].status == TaskStatus.WAITING_CONFIRMATION


def test_user_confirmation_resumes_and_persists_completed_plan(tmp_db_path: str) -> None:
    llm = CustomTestLLM(
        response_dict={
            "tasks": [
                {
                    "description": "Ejecutar comando peligroso",
                    "order": 1,
                    "tool_name": "dangerous",
                    "parameters": {"cmd": "format C:"},
                }
            ]
        }
    )
    cog, _, _, plan_store, _, dangerous = setup_cognition_environment(tmp_db_path, llm=llm)

    # 1. Trigger agentic goal -> WAITING_CONFIRMATION
    cog.process_cognitive_cycle("planifica ejecuta el comando peligroso")
    assert dangerous.count == 0

    # 2. User confirms with "sí"
    res_confirm = cog.process_cognitive_cycle("sí, hazlo")

    assert "Confirmación recibida" in res_confirm.summary
    assert dangerous.count == 1

    active = plan_store.list_active_plans()
    assert len(active) == 0  # Completed plan is no longer active


def test_user_cancellation_denies_task_and_persists_state(tmp_db_path: str) -> None:
    llm = CustomTestLLM(
        response_dict={
            "tasks": [
                {
                    "description": "Ejecutar comando peligroso",
                    "order": 1,
                    "tool_name": "dangerous",
                    "parameters": {"cmd": "destroy"},
                }
            ]
        }
    )
    cog, _, _, plan_store, _, dangerous = setup_cognition_environment(tmp_db_path, llm=llm)

    # 1. Trigger agentic goal -> WAITING_CONFIRMATION
    cog.process_cognitive_cycle("planifica ejecuta comando peligroso")

    # 2. User cancels with "no, cancela"
    res_cancel = cog.process_cognitive_cycle("no, cancela")

    assert "cancelada" in res_cancel.summary
    assert dangerous.count == 0

    active = plan_store.list_active_plans()
    assert len(active) == 0  # Failed/Cancelled plan is no longer active


def test_restart_simulation_during_waiting_confirmation(tmp_db_path: str) -> None:
    llm = CustomTestLLM(
        response_dict={
            "tasks": [
                {
                    "description": "Ejecutar comando peligroso",
                    "order": 1,
                    "tool_name": "dangerous",
                    "parameters": {"cmd": "wipe"},
                }
            ]
        }
    )

    # 1. Create first session and pause on WAITING_CONFIRMATION
    cog1, _, _, plan_store1, _, dangerous1 = setup_cognition_environment(tmp_db_path, llm=llm)
    cog1.process_cognitive_cycle("planifica ejecuta comando peligroso")
    assert dangerous1.count == 0

    # Close DB store to simulate restart
    plan_store1.store.close()

    # 2. Re-open session with new store & module instance
    cog2, _, _, plan_store2, _, dangerous2 = setup_cognition_environment(tmp_db_path, llm=llm)

    active_plans = plan_store2.list_active_plans()
    assert len(active_plans) == 1
    assert active_plans[0].is_waiting_confirmation() is True

    # 3. Confirm in second session
    res_confirm = cog2.process_cognitive_cycle("sí, confirma")

    assert "Confirmación recibida" in res_confirm.summary
    assert dangerous2.count == 1


def test_normal_conversational_turn_does_not_trigger_agent_planner(tmp_db_path: str) -> None:
    llm = CustomTestLLM()
    cog, _, _, plan_store, calc, dangerous = setup_cognition_environment(tmp_db_path, llm=llm)

    res = cog.process_cognitive_cycle("Hola, ¿cómo estás?")

    assert res is not None
    assert calc.count == 0
    assert dangerous.count == 0
    assert len(plan_store.list_active_plans()) == 0


def test_planner_failure_falls_back_to_reactive_cycle(tmp_db_path: str) -> None:
    # LLM raises an error during structured_reasoning
    class ErrorLLM(LLMProvider):
        def generate_response(
            self,
            prompt: str,
            system_instruction: str = "",
            context: dict[str, Any] | None = None,
        ) -> LLMResponse:
            return LLMResponse(content="Flujo reactivo de respaldo.")

        def structured_reason(
            self,
            prompt: str,
            schema: dict[str, Any] | None = None,
            context: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            raise ValueError("Inference error")

    cog, _, _, _, _, _ = setup_cognition_environment(tmp_db_path, llm=ErrorLLM())

    res = cog.process_cognitive_cycle("planifica algo imposible")

    assert res is not None
    assert "Flujo reactivo" in res.summary
