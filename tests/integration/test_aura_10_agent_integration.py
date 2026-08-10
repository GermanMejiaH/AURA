from __future__ import annotations

from aura.autonomy import (
    AgentExecutionResult,
    AgentExecutor,
    AgentGoal,
    AgentPlan,
    AgentTask,
    TaskStatus,
)
from aura.events import (
    AgentConfirmationDenied,
    AgentConfirmationGranted,
    AgentStepEvaluated,
    EventBus,
    ToolConfirmationRequired,
)
from aura.tools.base import BaseTool, ToolMetadata, ToolResult
from aura.tools.builtins import CalculatorTool, DateTimeTool, SystemStatusTool
from aura.tools.registry import ToolRegistry


class CustomDangerousTool(BaseTool):
    metadata = ToolMetadata(
        name="custom_dangerous",
        description="Paso peligroso de prueba",
        risk_level="destructive",
        requires_confirmation=True,
    )

    def execute(self, **kwargs: object) -> ToolResult:
        return ToolResult(success=True, output="Acción de riesgo ejecutada")


class CustomFailingTool(BaseTool):
    metadata = ToolMetadata(
        name="custom_fail",
        description="Paso que siempre falla",
    )

    def execute(self, **kwargs: object) -> ToolResult:
        return ToolResult(success=False, error="Error imprevisto en la herramienta")


def test_1_e2e_successful_multistep_flow() -> None:
    registry = ToolRegistry()
    registry.register(DateTimeTool())
    registry.register(CalculatorTool())
    registry.register(SystemStatusTool())

    goal = AgentGoal(description="Flujo de integración multi-step exitoso")

    t1 = AgentTask(
        description="Paso 1: Consultar hora",
        order=1,
        tool_name="datetime_tool",
        parameters={"action": "now"},
    )
    t2 = AgentTask(
        description="Paso 2: Calcular 150 * 4",
        order=2,
        tool_name="calculator_tool",
        parameters={"expression": "150 * 4"},
    )
    t3 = AgentTask(
        description="Paso 3: Verificar estado del sistema",
        order=3,
        tool_name="system_status_tool",
        parameters={},
    )

    plan = AgentPlan(goal=goal, tasks=[t1, t2, t3])
    executor = AgentExecutor(registry=registry)

    res: AgentExecutionResult = executor.execute_plan(plan)

    assert res.completed is True
    assert res.failed is False
    assert res.steps_executed == 3
    assert len(res.executed_tasks) == 3

    assert t1.status == TaskStatus.SUCCESS
    assert t1.result is not None

    assert t2.status == TaskStatus.SUCCESS
    assert t2.result == 600

    assert t3.status == TaskStatus.SUCCESS
    assert isinstance(t3.result, dict) or t3.result is not None


def test_2_e2e_real_tool_registry_use() -> None:
    registry = ToolRegistry()
    registry.register(DateTimeTool())
    registry.register(CalculatorTool())
    registry.register(SystemStatusTool())

    assert registry.get("datetime_tool") is not None
    assert registry.get("calculator_tool") is not None
    assert registry.get("system_status_tool") is not None

    t1 = AgentTask(
        description="Calc",
        order=1,
        tool_name="calculator_tool",
        parameters={"expression": "25 * 4"},
    )
    plan = AgentPlan(goal=AgentGoal(description="Uso real"), tasks=[t1])

    executor = AgentExecutor(registry=registry)
    res = executor.execute_plan(plan)

    assert res.completed is True
    assert t1.result == 100


def test_3_e2e_observation_to_evaluation_flow() -> None:
    event_bus = EventBus()
    step_evaluated_events: list[AgentStepEvaluated] = []

    def on_step_evaluated(event: AgentStepEvaluated) -> None:
        step_evaluated_events.append(event)

    event_bus.subscribe(AgentStepEvaluated, on_step_evaluated)

    registry = ToolRegistry()
    registry.register(CalculatorTool())

    t1 = AgentTask(
        description="Suma",
        order=1,
        tool_name="calculator_tool",
        parameters={"expression": "75 + 25"},
    )
    plan = AgentPlan(goal=AgentGoal(description="Flujo de Evaluación"), tasks=[t1])

    executor = AgentExecutor(event_bus=event_bus, registry=registry)
    res = executor.execute_plan(plan)

    assert res.completed is True
    assert t1.status == TaskStatus.SUCCESS
    assert len(step_evaluated_events) == 1

    evt = step_evaluated_events[0]
    assert evt.task_id == t1.task_id
    assert evt.evaluation_status == "SUCCESS"
    assert "completed successfully" in evt.reason


def test_4_e2e_failure_in_middle_of_plan() -> None:
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(CustomFailingTool())

    t1 = AgentTask(
        description="Paso 1 seguro",
        order=1,
        tool_name="calculator_tool",
        parameters={"expression": "10 + 10"},
    )
    t2 = AgentTask(description="Paso 2 con fallo", order=2, tool_name="custom_fail")
    t3 = AgentTask(description="Paso 3 posterior", order=3)

    plan = AgentPlan(goal=AgentGoal(description="Plan con fallo"), tasks=[t1, t2, t3])
    executor = AgentExecutor(registry=registry)

    res = executor.execute_plan(plan)

    assert res.completed is False
    assert res.failed is True
    assert res.steps_executed == 2

    assert t1.status == TaskStatus.SUCCESS
    assert t1.result == 20

    assert t2.status == TaskStatus.FAILED
    assert "Error imprevisto" in str(t2.error)

    assert t3.status == TaskStatus.PENDING


def test_5_e2e_human_confirmation_and_resumption() -> None:
    event_bus = EventBus()
    conf_requested_events: list[ToolConfirmationRequired] = []
    conf_granted_events: list[AgentConfirmationGranted] = []

    def on_conf_requested(evt: ToolConfirmationRequired) -> None:
        conf_requested_events.append(evt)

    def on_conf_granted(evt: AgentConfirmationGranted) -> None:
        conf_granted_events.append(evt)

    event_bus.subscribe(ToolConfirmationRequired, on_conf_requested)
    event_bus.subscribe(AgentConfirmationGranted, on_conf_granted)

    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(CustomDangerousTool())

    t1 = AgentTask(
        description="Paso 1",
        order=1,
        tool_name="calculator_tool",
        parameters={"expression": "5 * 5"},
    )
    t2 = AgentTask(description="Paso 2 peligroso", order=2, tool_name="custom_dangerous")
    t3 = AgentTask(
        description="Paso 3 posterior",
        order=3,
        tool_name="calculator_tool",
        parameters={"expression": "100 + 100"},
    )

    plan = AgentPlan(goal=AgentGoal(description="Flujo Confirmación"), tasks=[t1, t2, t3])
    executor = AgentExecutor(event_bus=event_bus, registry=registry)

    # First run: pauses at t2
    res1 = executor.execute_plan(plan)
    assert res1.waiting_confirmation is True
    assert res1.completed is False
    assert t1.status == TaskStatus.SUCCESS
    assert t2.status == TaskStatus.WAITING_CONFIRMATION
    assert t3.status == TaskStatus.PENDING
    assert len(conf_requested_events) == 1

    # Authorize t2
    ok = executor.authorize_task(plan, task_id=t2.task_id)
    assert ok is True
    assert len(conf_granted_events) == 1
    assert conf_granted_events[0].task_id == t2.task_id

    # Resume execution
    res2 = executor.resume_plan(plan)
    assert res2.completed is True
    assert res2.failed is False
    assert t1.result == 25
    assert t2.status == TaskStatus.SUCCESS
    assert t2.result == "Acción de riesgo ejecutada"
    assert t3.status == TaskStatus.SUCCESS
    assert t3.result == 200


def test_6_e2e_denial_flow() -> None:
    event_bus = EventBus()
    denied_events: list[AgentConfirmationDenied] = []

    def on_denied(evt: AgentConfirmationDenied) -> None:
        denied_events.append(evt)

    event_bus.subscribe(AgentConfirmationDenied, on_denied)

    registry = ToolRegistry()
    registry.register(CustomDangerousTool())

    t1 = AgentTask(description="Paso destructivo", order=1, tool_name="custom_dangerous")
    t2 = AgentTask(description="Paso no alcanzado", order=2)

    plan = AgentPlan(goal=AgentGoal(description="Flujo Denegación"), tasks=[t1, t2])
    executor = AgentExecutor(event_bus=event_bus, registry=registry)

    _ = executor.execute_plan(plan)
    assert t1.status == TaskStatus.WAITING_CONFIRMATION

    ok = executor.deny_task(plan, task_id=t1.task_id, reason="Denegado por usuario")
    assert ok is True
    assert len(denied_events) == 1
    assert denied_events[0].reason == "Denegado por usuario"

    res = executor.resume_plan(plan)
    assert res.failed is True
    assert res.completed is False
    assert t1.status == TaskStatus.FAILED
    assert t2.status == TaskStatus.PENDING


def test_7_e2e_multiple_dangerous_tools_require_individual_confirmations() -> None:
    registry = ToolRegistry()
    registry.register(CustomDangerousTool())

    t1 = AgentTask(description="Riesgo A", order=1, tool_name="custom_dangerous")
    t2 = AgentTask(description="Riesgo B", order=2, tool_name="custom_dangerous")

    plan = AgentPlan(goal=AgentGoal(description="Doble Confirmación"), tasks=[t1, t2])
    executor = AgentExecutor(registry=registry)

    # Pause at t1
    _ = executor.execute_plan(plan)
    assert t1.status == TaskStatus.WAITING_CONFIRMATION

    # Confirm t1 -> Resume -> Pause at t2
    executor.authorize_task(plan, task_id=t1.task_id)
    res2 = executor.resume_plan(plan)

    assert t1.status == TaskStatus.SUCCESS
    assert t2.status == TaskStatus.WAITING_CONFIRMATION
    assert res2.waiting_confirmation is True


def test_8_e2e_max_agent_steps_safety_limit() -> None:
    registry = ToolRegistry()
    registry.register(CalculatorTool())

    tasks = [
        AgentTask(
            description=f"Calc {i}",
            order=i,
            tool_name="calculator_tool",
            parameters={"expression": f"{i} * 2"},
        )
        for i in range(1, 8)
    ]
    plan = AgentPlan(goal=AgentGoal(description="Límite max_steps"), tasks=tasks)

    executor = AgentExecutor(max_agent_steps=4, registry=registry)
    res1 = executor.execute_plan(plan)

    assert res1.steps_executed == 4
    assert res1.completed is False
    assert tasks[3].status == TaskStatus.SUCCESS
    assert tasks[4].status == TaskStatus.PENDING

    # Second resume executes remaining 3
    res2 = executor.resume_plan(plan)
    assert res2.steps_executed == 3
    assert res2.completed is True
    assert tasks[6].status == TaskStatus.SUCCESS


def test_9_e2e_execution_determinism() -> None:
    registry = ToolRegistry()
    registry.register(CalculatorTool())

    t1 = AgentTask(
        description="Determinismo",
        order=1,
        tool_name="calculator_tool",
        parameters={"expression": "12 * 12"},
    )
    plan = AgentPlan(goal=AgentGoal(description="Determinista"), tasks=[t1])

    executor = AgentExecutor(registry=registry)
    res1 = executor.execute_plan(plan)
    res2 = executor.execute_plan(plan)

    assert res1.completed is True
    assert res2.completed is True
    assert t1.result == 144
