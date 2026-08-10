from __future__ import annotations

from aura.autonomy import AgentExecutor, AgentGoal, AgentPlan, AgentTask, TaskStatus
from aura.tools.base import BaseTool, ToolMetadata, ToolResult
from aura.tools.builtins import CalculatorTool, DateTimeTool
from aura.tools.registry import ToolRegistry


class DestructiveTestTool(BaseTool):
    metadata = ToolMetadata(
        name="destructive_tool",
        description="Destructive test tool",
        risk_level="destructive",
        requires_confirmation=True,
    )

    def execute(self, **kwargs: object) -> ToolResult:
        return ToolResult.success("Executed")


class FailingTestTool(BaseTool):
    metadata = ToolMetadata(
        name="failing_tool",
        description="Always fails",
    )

    def execute(self, **kwargs: object) -> ToolResult:
        return ToolResult(success=False, error="Connection error")


def test_1_executes_one_task_correctly() -> None:
    registry = ToolRegistry()
    registry.register(DateTimeTool())

    goal = AgentGoal(description="Obtener hora")
    task = AgentTask(
        description="Consultar hora",
        order=1,
        tool_name="datetime_tool",
        parameters={"action": "now"},
    )
    plan = AgentPlan(goal=goal, tasks=[task])

    executor = AgentExecutor(registry=registry)
    res = executor.execute_plan(plan)

    assert res.steps_executed == 1
    assert res.completed is True
    assert res.failed is False
    assert task.status == TaskStatus.SUCCESS
    assert task.result is not None


def test_2_executes_three_sequential_tasks() -> None:
    registry = ToolRegistry()
    registry.register(DateTimeTool())
    registry.register(CalculatorTool())

    goal = AgentGoal(description="Flujo de 3 tareas")
    t1 = AgentTask(
        description="Paso 1: Hora",
        order=1,
        tool_name="datetime_tool",
        parameters={"action": "now"},
    )
    t2 = AgentTask(
        description="Paso 2: Cálculo",
        order=2,
        tool_name="calculator_tool",
        parameters={"expression": "100 + 50"},
    )
    t3 = AgentTask(description="Paso 3: Tarea sin tool", order=3)

    plan = AgentPlan(goal=goal, tasks=[t1, t2, t3])
    executor = AgentExecutor(registry=registry)
    res = executor.execute_plan(plan)

    assert res.steps_executed == 3
    assert res.completed is True
    assert res.failed is False
    assert t1.status == TaskStatus.SUCCESS
    assert t2.status == TaskStatus.SUCCESS
    assert t2.result == 150
    assert t3.status == TaskStatus.SUCCESS


def test_3_respects_order_of_execution() -> None:
    registry = ToolRegistry()
    registry.register(CalculatorTool())

    t2 = AgentTask(
        description="Paso 2",
        order=2,
        tool_name="calculator_tool",
        parameters={"expression": "10 * 2"},
    )
    t1 = AgentTask(
        description="Paso 1",
        order=1,
        tool_name="calculator_tool",
        parameters={"expression": "5 + 5"},
    )

    plan = AgentPlan(goal=AgentGoal(description="Orden"), tasks=[t2, t1])
    executor = AgentExecutor(registry=registry)
    res = executor.execute_plan(plan)

    assert res.steps_executed == 2
    assert res.executed_tasks[0].order == 1
    assert res.executed_tasks[1].order == 2


def test_4_does_not_reexecute_success_tasks() -> None:
    registry = ToolRegistry()
    registry.register(DateTimeTool())

    t1 = AgentTask(
        description="Paso 1 ya listo",
        order=1,
        status=TaskStatus.SUCCESS,
        tool_name="datetime_tool",
        result="20:00",
    )
    t2 = AgentTask(
        description="Paso 2 pendiente",
        order=2,
        tool_name="datetime_tool",
        parameters={"action": "date"},
    )

    plan = AgentPlan(goal=AgentGoal(description="Re-ejecución"), tasks=[t1, t2])
    executor = AgentExecutor(registry=registry)
    res = executor.execute_plan(plan)

    assert res.steps_executed == 1
    assert res.executed_tasks == [t2]
    assert t1.result == "20:00"
    assert t2.status == TaskStatus.SUCCESS


def test_5_failed_task_stops_plan() -> None:
    registry = ToolRegistry()
    registry.register(FailingTestTool())
    registry.register(DateTimeTool())

    t1 = AgentTask(description="Tarea fallida", order=1, tool_name="failing_tool")
    t2 = AgentTask(
        description="Tarea posterior",
        order=2,
        tool_name="datetime_tool",
        parameters={"action": "now"},
    )

    plan = AgentPlan(goal=AgentGoal(description="Fallo"), tasks=[t1, t2])
    executor = AgentExecutor(registry=registry)
    res = executor.execute_plan(plan)

    assert res.failed is True
    assert res.completed is False
    assert res.steps_executed == 1
    assert t1.status == TaskStatus.FAILED
    assert t2.status == TaskStatus.PENDING


def test_6_waiting_confirmation_stops_plan() -> None:
    registry = ToolRegistry()
    registry.register(DestructiveTestTool())

    t1 = AgentTask(description="Destruir datos", order=1, tool_name="destructive_tool")
    t2 = AgentTask(description="Tarea 2", order=2)

    plan = AgentPlan(goal=AgentGoal(description="Peligro"), tasks=[t1, t2])
    executor = AgentExecutor(registry=registry)
    res = executor.execute_plan(plan)

    assert res.waiting_confirmation is True
    assert res.completed is False
    assert t1.status == TaskStatus.WAITING_CONFIRMATION
    assert t2.status == TaskStatus.PENDING


def test_7_respects_max_agent_steps_default_5() -> None:
    tasks = [AgentTask(description=f"Tarea {i}", order=i) for i in range(1, 8)]
    plan = AgentPlan(goal=AgentGoal(description="Largo"), tasks=tasks)

    executor = AgentExecutor(max_agent_steps=5)
    res = executor.execute_plan(plan)

    assert res.steps_executed == 5
    assert res.completed is False
    assert tasks[4].status == TaskStatus.SUCCESS
    assert tasks[5].status == TaskStatus.PENDING


def test_8_plan_with_more_than_5_tasks_executes_at_most_5() -> None:
    tasks = [AgentTask(description=f"Paso {i}", order=i) for i in range(1, 10)]
    plan = AgentPlan(goal=AgentGoal(description="Muchos pasos"), tasks=tasks)

    executor = AgentExecutor(max_agent_steps=5)
    res = executor.execute_plan(plan)

    assert res.steps_executed == 5
    assert len(res.executed_tasks) == 5


def test_9_tool_error_recorded_in_task_error() -> None:
    registry = ToolRegistry()
    registry.register(FailingTestTool())

    t1 = AgentTask(description="Fallo de red", order=1, tool_name="failing_tool")
    plan = AgentPlan(goal=AgentGoal(description="Test error"), tasks=[t1])

    executor = AgentExecutor(registry=registry)
    _ = executor.execute_plan(plan)

    assert t1.status == TaskStatus.FAILED
    assert t1.error == "Connection error"


def test_10_no_subsequent_tasks_executed_after_failed() -> None:
    registry = ToolRegistry()
    registry.register(FailingTestTool())

    t1 = AgentTask(description="Paso 1 (Falla)", order=1, tool_name="failing_tool")
    t2 = AgentTask(description="Paso 2", order=2)
    t3 = AgentTask(description="Paso 3", order=3)

    plan = AgentPlan(goal=AgentGoal(description="Test fallo"), tasks=[t1, t2, t3])
    executor = AgentExecutor(registry=registry)
    res = executor.execute_plan(plan)

    assert res.steps_executed == 1
    assert t1.status == TaskStatus.FAILED
    assert t2.status == TaskStatus.PENDING
    assert t3.status == TaskStatus.PENDING


def test_11_no_subsequent_tasks_executed_after_waiting_confirmation() -> None:
    registry = ToolRegistry()
    registry.register(DestructiveTestTool())

    t1 = AgentTask(description="Paso destructivo", order=1, tool_name="destructive_tool")
    t2 = AgentTask(description="Paso siguiente", order=2)

    plan = AgentPlan(goal=AgentGoal(description="Test pausa"), tasks=[t1, t2])
    executor = AgentExecutor(registry=registry)
    res = executor.execute_plan(plan)

    assert res.steps_executed == 1
    assert t1.status == TaskStatus.WAITING_CONFIRMATION
    assert t2.status == TaskStatus.PENDING


def test_12_empty_plan_finishes_cleanly() -> None:
    plan = AgentPlan(goal=AgentGoal(description="Plan vacío"), tasks=[])
    executor = AgentExecutor()
    res = executor.execute_plan(plan)

    assert res.completed is True
    assert res.steps_executed == 0
    assert res.failed is False
    assert res.waiting_confirmation is False


def test_13_execution_is_deterministic() -> None:
    registry = ToolRegistry()
    registry.register(CalculatorTool())

    t1 = AgentTask(
        description="Calc 1",
        order=1,
        tool_name="calculator_tool",
        parameters={"expression": "2 + 2"},
    )
    t2 = AgentTask(
        description="Calc 2",
        order=2,
        tool_name="calculator_tool",
        parameters={"expression": "5 * 5"},
    )

    plan1 = AgentPlan(goal=AgentGoal(description="Plan 1"), tasks=[t1, t2])
    executor = AgentExecutor(registry=registry)
    res1 = executor.execute_plan(plan1)

    assert res1.completed is True
    assert t1.result == 4
    assert t2.result == 25


def test_14_zero_llm_calls_performed() -> None:
    # AgentExecutor does pure deterministic tool calls without LLM provider
    executor = AgentExecutor()
    plan = AgentPlan(goal=AgentGoal(description="Meta"), tasks=[AgentTask(description="Task 1")])
    res = executor.execute_plan(plan)
    assert res.completed is True


def test_15_zero_sqlite_modifications() -> None:
    # AgentExecutor interacts only in RAM with AgentPlan and ToolRegistry
    executor = AgentExecutor()
    plan = AgentPlan(
        goal=AgentGoal(description="Meta en RAM"), tasks=[AgentTask(description="Task")]
    )
    res = executor.execute_plan(plan)
    assert res.completed is True


def test_16_full_compatibility_with_tool_registry_builtins() -> None:
    registry = ToolRegistry()
    registry.register(DateTimeTool())
    registry.register(CalculatorTool())

    t1 = AgentTask(
        description="Consultar fecha",
        order=1,
        tool_name="datetime_tool",
        parameters={"action": "date"},
    )
    t2 = AgentTask(
        description="Calcular suma",
        order=2,
        tool_name="calculator_tool",
        parameters={"expression": "125 * 37"},
    )

    plan = AgentPlan(goal=AgentGoal(description="Herramientas reales"), tasks=[t1, t2])
    executor = AgentExecutor(registry=registry)
    res = executor.execute_plan(plan)

    assert res.completed is True
    assert res.steps_executed == 2
    assert t1.status == TaskStatus.SUCCESS
    assert t2.status == TaskStatus.SUCCESS
    assert t2.result == 4625
