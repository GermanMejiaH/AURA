from __future__ import annotations

from aura.autonomy import AgentExecutor, AgentGoal, AgentPlan, AgentTask, TaskStatus
from aura.events import (
    AgentConfirmationDenied,
    AgentConfirmationGranted,
    EventBus,
    ToolConfirmationRequired,
)
from aura.tools.base import BaseTool, ToolMetadata, ToolResult
from aura.tools.builtins import CalculatorTool, DateTimeTool
from aura.tools.registry import ToolRegistry


class DestructiveTool(BaseTool):
    metadata = ToolMetadata(
        name="destructive_tool",
        description="Destructive action",
        risk_level="destructive",
    )

    def execute(self, **kwargs: object) -> ToolResult:
        return ToolResult(success=True, output="Destructive action completed")


class RequiresConfirmationTool(BaseTool):
    metadata = ToolMetadata(
        name="confirm_tool",
        description="Action requiring confirmation",
        requires_confirmation=True,
    )

    def execute(self, **kwargs: object) -> ToolResult:
        return ToolResult(success=True, output="Action with confirmation completed")


def test_1_safe_tool_executes_normally() -> None:
    registry = ToolRegistry()
    registry.register(DateTimeTool())

    t1 = AgentTask(
        description="Paso seguro", order=1, tool_name="datetime_tool", parameters={"action": "now"}
    )
    plan = AgentPlan(goal=AgentGoal(description="Seguro"), tasks=[t1])

    executor = AgentExecutor(registry=registry)
    res = executor.execute_plan(plan)

    assert res.completed is True
    assert t1.status == TaskStatus.SUCCESS


def test_2_requires_confirmation_tool_blocks_execution() -> None:
    registry = ToolRegistry()
    registry.register(RequiresConfirmationTool())

    t1 = AgentTask(description="Paso peligroso", order=1, tool_name="confirm_tool")
    plan = AgentPlan(goal=AgentGoal(description="Bloqueo 1"), tasks=[t1])

    executor = AgentExecutor(registry=registry)
    res = executor.execute_plan(plan)

    assert res.waiting_confirmation is True
    assert res.completed is False
    assert t1.status == TaskStatus.WAITING_CONFIRMATION


def test_3_destructive_risk_level_tool_blocks_execution() -> None:
    registry = ToolRegistry()
    registry.register(DestructiveTool())

    t1 = AgentTask(description="Paso destructivo", order=1, tool_name="destructive_tool")
    plan = AgentPlan(goal=AgentGoal(description="Bloqueo 2"), tasks=[t1])

    executor = AgentExecutor(registry=registry)
    res = executor.execute_plan(plan)

    assert res.waiting_confirmation is True
    assert res.completed is False
    assert t1.status == TaskStatus.WAITING_CONFIRMATION


def test_4_waiting_confirmation_registered_in_task_and_plan() -> None:
    registry = ToolRegistry()
    registry.register(DestructiveTool())

    t1 = AgentTask(description="Acción destructiva", order=1, tool_name="destructive_tool")
    plan = AgentPlan(goal=AgentGoal(description="Test Estado"), tasks=[t1])

    executor = AgentExecutor(registry=registry)
    res = executor.execute_plan(plan)

    assert plan.is_waiting_confirmation() is True
    assert res.waiting_confirmation is True
    assert t1.status == TaskStatus.WAITING_CONFIRMATION


def test_5_tool_confirmation_required_event_emitted() -> None:
    event_bus = EventBus()
    events: list[ToolConfirmationRequired] = []

    def handler(event: ToolConfirmationRequired) -> None:
        events.append(event)

    event_bus.subscribe(ToolConfirmationRequired, handler)

    registry = ToolRegistry()
    registry.register(DestructiveTool())

    t1 = AgentTask(description="Paso evento", order=1, tool_name="destructive_tool")
    plan = AgentPlan(goal=AgentGoal(description="Evento"), tasks=[t1])

    executor = AgentExecutor(event_bus=event_bus, registry=registry)
    _ = executor.execute_plan(plan)

    assert len(events) == 1
    assert events[0].tool_name == "destructive_tool"
    assert events[0].risk_level == "destructive"


def test_6_invalid_confirmation_wrong_task_id_rejected() -> None:
    registry = ToolRegistry()
    registry.register(DestructiveTool())

    t1 = AgentTask(description="Paso destructivo", order=1, tool_name="destructive_tool")
    plan = AgentPlan(goal=AgentGoal(description="Wrong task"), tasks=[t1])

    executor = AgentExecutor(registry=registry)
    _ = executor.execute_plan(plan)

    ok = executor.authorize_task(plan, task_id="task_inexistente")
    assert ok is False
    assert t1.status == TaskStatus.WAITING_CONFIRMATION


def test_7_invalid_confirmation_wrong_plan_rejected() -> None:
    registry = ToolRegistry()
    registry.register(DestructiveTool())

    t1 = AgentTask(description="Paso destructivo", order=1, tool_name="destructive_tool")
    plan1 = AgentPlan(goal=AgentGoal(description="Plan 1"), tasks=[t1])
    plan2 = AgentPlan(goal=AgentGoal(description="Plan 2"), tasks=[])

    executor = AgentExecutor(registry=registry)
    _ = executor.execute_plan(plan1)

    ok = executor.authorize_task(plan2, task_id=t1.task_id)
    assert ok is False
    assert t1.status == TaskStatus.WAITING_CONFIRMATION


def test_8_cannot_confirm_task_not_waiting_confirmation() -> None:
    t1 = AgentTask(description="Paso pendiente simple", order=1)
    plan = AgentPlan(goal=AgentGoal(description="No waiting"), tasks=[t1])

    executor = AgentExecutor()
    ok = executor.authorize_task(plan, task_id=t1.task_id)
    assert ok is False


def test_9_valid_confirmation_allows_executing_task() -> None:
    event_bus = EventBus()
    granted_events: list[AgentConfirmationGranted] = []

    def handler(event: AgentConfirmationGranted) -> None:
        granted_events.append(event)

    event_bus.subscribe(AgentConfirmationGranted, handler)

    registry = ToolRegistry()
    registry.register(DestructiveTool())

    t1 = AgentTask(description="Borrar BD", order=1, tool_name="destructive_tool")
    plan = AgentPlan(goal=AgentGoal(description="Confirmación válida"), tasks=[t1])

    executor = AgentExecutor(event_bus=event_bus, registry=registry)
    _ = executor.execute_plan(plan)
    assert t1.status == TaskStatus.WAITING_CONFIRMATION

    ok = executor.authorize_task(plan, task_id=t1.task_id)
    assert ok is True
    assert len(granted_events) == 1
    assert granted_events[0].task_id == t1.task_id

    res = executor.resume_plan(plan)
    assert res.completed is True
    assert t1.status == TaskStatus.SUCCESS
    assert t1.result == "Destructive action completed"


def test_10_previous_success_tasks_not_repeated() -> None:
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(DestructiveTool())

    t1 = AgentTask(
        description="Calc seguro",
        order=1,
        tool_name="calculator_tool",
        parameters={"expression": "50 + 50"},
    )
    t2 = AgentTask(description="Destructivo", order=2, tool_name="destructive_tool")

    plan = AgentPlan(goal=AgentGoal(description="Reinicio seguro"), tasks=[t1, t2])
    executor = AgentExecutor(registry=registry)

    # First run stops at t2
    res1 = executor.execute_plan(plan)
    assert res1.steps_executed == 2
    assert t1.status == TaskStatus.SUCCESS
    assert t2.status == TaskStatus.WAITING_CONFIRMATION

    # Authorize t2 and resume
    executor.authorize_task(plan, task_id=t2.task_id)
    res2 = executor.resume_plan(plan)

    assert res2.steps_executed == 1
    assert res2.executed_tasks == [t2]
    assert t1.result == 100
    assert t2.status == TaskStatus.SUCCESS


def test_11_subsequent_tasks_not_executed_before_confirmation() -> None:
    registry = ToolRegistry()
    registry.register(DestructiveTool())
    registry.register(CalculatorTool())

    t1 = AgentTask(description="Destructivo", order=1, tool_name="destructive_tool")
    t2 = AgentTask(
        description="Calc posterior",
        order=2,
        tool_name="calculator_tool",
        parameters={"expression": "10 * 10"},
    )

    plan = AgentPlan(goal=AgentGoal(description="Pausa estricta"), tasks=[t1, t2])
    executor = AgentExecutor(registry=registry)
    res = executor.execute_plan(plan)

    assert res.waiting_confirmation is True
    assert t1.status == TaskStatus.WAITING_CONFIRMATION
    assert t2.status == TaskStatus.PENDING


def test_12_subsequent_tasks_can_execute_after_confirmation() -> None:
    registry = ToolRegistry()
    registry.register(DestructiveTool())
    registry.register(CalculatorTool())

    t1 = AgentTask(description="Destructivo", order=1, tool_name="destructive_tool")
    t2 = AgentTask(
        description="Calc posterior",
        order=2,
        tool_name="calculator_tool",
        parameters={"expression": "10 * 10"},
    )

    plan = AgentPlan(goal=AgentGoal(description="Continuación posterior"), tasks=[t1, t2])
    executor = AgentExecutor(registry=registry)

    _ = executor.execute_plan(plan)
    executor.authorize_task(plan, task_id=t1.task_id)
    res = executor.resume_plan(plan)

    assert res.completed is True
    assert t1.status == TaskStatus.SUCCESS
    assert t2.status == TaskStatus.SUCCESS
    assert t2.result == 100


def test_13_second_dangerous_task_requires_separate_confirmation() -> None:
    registry = ToolRegistry()
    registry.register(DestructiveTool())

    t1 = AgentTask(description="Paso 1 destructivo", order=1, tool_name="destructive_tool")
    t2 = AgentTask(description="Paso 2 destructivo", order=2, tool_name="destructive_tool")

    plan = AgentPlan(goal=AgentGoal(description="Doble riesgo"), tasks=[t1, t2])
    executor = AgentExecutor(registry=registry)

    _ = executor.execute_plan(plan)
    assert t1.status == TaskStatus.WAITING_CONFIRMATION

    # Confirm t1
    executor.authorize_task(plan, task_id=t1.task_id)
    res2 = executor.resume_plan(plan)

    # Must execute t1 and then pause at t2!
    assert t1.status == TaskStatus.SUCCESS
    assert t2.status == TaskStatus.WAITING_CONFIRMATION
    assert res2.waiting_confirmation is True


def test_14_confirming_task_1_does_not_authorize_task_2() -> None:
    registry = ToolRegistry()
    registry.register(RequiresConfirmationTool())

    t1 = AgentTask(description="Task 1", order=1, tool_name="confirm_tool")
    t2 = AgentTask(description="Task 2", order=2, tool_name="confirm_tool")

    plan = AgentPlan(goal=AgentGoal(description="Aislamiento autorizaciones"), tasks=[t1, t2])
    executor = AgentExecutor(registry=registry)

    _ = executor.execute_plan(plan)
    executor.authorize_task(plan, task_id=t1.task_id)
    _ = executor.resume_plan(plan)

    assert t1.status == TaskStatus.SUCCESS
    assert t2.status == TaskStatus.WAITING_CONFIRMATION
    assert t2.parameters.get("_authorized") is not True


def test_15_denial_does_not_continue_plan_and_sets_failed() -> None:
    event_bus = EventBus()
    denied_events: list[AgentConfirmationDenied] = []

    def handler(event: AgentConfirmationDenied) -> None:
        denied_events.append(event)

    event_bus.subscribe(AgentConfirmationDenied, handler)

    registry = ToolRegistry()
    registry.register(DestructiveTool())

    t1 = AgentTask(description="Acción peligrosa", order=1, tool_name="destructive_tool")
    t2 = AgentTask(description="Tarea posterior", order=2)

    plan = AgentPlan(goal=AgentGoal(description="Negativa"), tasks=[t1, t2])
    executor = AgentExecutor(event_bus=event_bus, registry=registry)

    _ = executor.execute_plan(plan)
    assert t1.status == TaskStatus.WAITING_CONFIRMATION

    ok = executor.deny_task(plan, task_id=t1.task_id, reason="Usuario rechazó la acción")
    assert ok is True
    assert len(denied_events) == 1
    assert denied_events[0].reason == "Usuario rechazó la acción"
    assert t1.status == TaskStatus.FAILED
    assert "Confirmation denied" in str(t1.error)

    res2 = executor.resume_plan(plan)
    assert res2.failed is True
    assert res2.completed is False
    assert t2.status == TaskStatus.PENDING


def test_16_max_agent_steps_continues_working_after_resume() -> None:
    tasks = [AgentTask(description=f"Paso {i}", order=i) for i in range(1, 8)]
    plan = AgentPlan(goal=AgentGoal(description="Max steps resume"), tasks=tasks)

    executor = AgentExecutor(max_agent_steps=3)
    res1 = executor.execute_plan(plan)

    assert res1.steps_executed == 3
    assert tasks[2].status == TaskStatus.SUCCESS
    assert tasks[3].status == TaskStatus.PENDING

    res2 = executor.resume_plan(plan)
    assert res2.steps_executed == 3
    assert tasks[5].status == TaskStatus.SUCCESS
    assert tasks[6].status == TaskStatus.PENDING


def test_17_zero_llm_calls_for_confirmation_and_resumption() -> None:
    registry = ToolRegistry()
    registry.register(DestructiveTool())

    t1 = AgentTask(description="Task 1", order=1, tool_name="destructive_tool")
    plan = AgentPlan(goal=AgentGoal(description="Pura RAM"), tasks=[t1])

    executor = AgentExecutor(registry=registry)
    _ = executor.execute_plan(plan)
    executor.authorize_task(plan, task_id=t1.task_id)
    res = executor.resume_plan(plan)

    assert res.completed is True


def test_18_zero_sqlite_modifications() -> None:
    executor = AgentExecutor()
    t1 = AgentTask(description="RAM Task", order=1, status=TaskStatus.WAITING_CONFIRMATION)
    plan = AgentPlan(goal=AgentGoal(description="RAM Goal"), tasks=[t1])

    executor.authorize_task(plan, task_id=t1.task_id)
    res = executor.resume_plan(plan)
    assert res.completed is True


def test_19_no_direct_execution_outside_tool_registry() -> None:
    registry = ToolRegistry()
    registry.register(DestructiveTool())

    t1 = AgentTask(description="Tool reg check", order=1, tool_name="destructive_tool")
    plan = AgentPlan(goal=AgentGoal(description="Registry check"), tasks=[t1])

    executor = AgentExecutor(registry=registry)
    _ = executor.execute_plan(plan)
    executor.authorize_task(plan, task_id=t1.task_id)
    res = executor.resume_plan(plan)

    assert res.completed is True
    assert t1.result == "Destructive action completed"


def test_20_deterministic_behavior() -> None:
    registry = ToolRegistry()
    registry.register(DestructiveTool())

    t1 = AgentTask(description="Task 1", order=1, tool_name="destructive_tool")
    plan1 = AgentPlan(goal=AgentGoal(description="Plan 1"), tasks=[t1])

    executor = AgentExecutor(registry=registry)
    _ = executor.execute_plan(plan1)
    executor.authorize_task(plan1, task_id=t1.task_id)
    res1 = executor.resume_plan(plan1)

    assert res1.completed is True
    assert t1.status == TaskStatus.SUCCESS
