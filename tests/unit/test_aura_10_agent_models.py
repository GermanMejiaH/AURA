from __future__ import annotations

import copy

from aura.autonomy import AgentGoal, AgentPlan, AgentTask, TaskStatus


def test_1_valid_agent_goal_creation() -> None:
    goal = AgentGoal(description="Organizar archivos de respaldo")
    assert goal.description == "Organizar archivos de respaldo"
    assert goal.goal_id.startswith("goal_")
    assert goal.status == TaskStatus.PENDING


def test_2_valid_agent_task_creation() -> None:
    task = AgentTask(
        description="Consultar el estado del sistema",
        order=1,
        tool_name="SystemStatusTool",
        parameters={"action": "full"},
    )
    assert task.description == "Consultar el estado del sistema"
    assert task.task_id.startswith("task_")
    assert task.order == 1
    assert task.tool_name == "SystemStatusTool"
    assert task.parameters == {"action": "full"}
    assert task.status == TaskStatus.PENDING


def test_3_valid_agent_plan_creation() -> None:
    goal = AgentGoal(description="Calcular costo total")
    task1 = AgentTask(description="Calcular 150 * 4", order=1, tool_name="CalculatorTool")
    plan = AgentPlan(goal=goal, tasks=[task1])

    assert plan.plan_id.startswith("plan_")
    assert plan.goal.description == "Calcular costo total"
    assert len(plan.tasks) == 1
    assert plan.tasks[0].description == "Calcular 150 * 4"


def test_4_agent_task_starts_in_pending() -> None:
    task = AgentTask(description="Revisar memoria")
    assert task.status == TaskStatus.PENDING


def test_5_agent_plan_preserves_task_order() -> None:
    t2 = AgentTask(description="Paso 2: Ejecutar cálculo", order=2)
    t1 = AgentTask(description="Paso 1: Consultar estado", order=1)
    t3 = AgentTask(description="Paso 3: Generar resumen", order=3)

    # Insert out of order
    plan = AgentPlan(goal=AgentGoal(description="Meta"), tasks=[t2, t1, t3])

    ordered = plan.get_ordered_tasks()
    assert [t.order for t in ordered] == [1, 2, 3]
    assert [t.description for t in ordered] == [
        "Paso 1: Consultar estado",
        "Paso 2: Ejecutar cálculo",
        "Paso 3: Generar resumen",
    ]


def test_6_get_next_pending_task_is_deterministic() -> None:
    t1 = AgentTask(description="Paso 1", order=1)
    t2 = AgentTask(description="Paso 2", order=2)
    plan = AgentPlan(goal=AgentGoal(description="Meta"), tasks=[t2, t1])

    next_task = plan.get_next_pending_task()
    assert next_task is not None
    assert next_task.order == 1
    assert next_task.description == "Paso 1"


def test_7_success_task_no_longer_pending() -> None:
    t1 = AgentTask(description="Paso 1", order=1, status=TaskStatus.SUCCESS)
    t2 = AgentTask(description="Paso 2", order=2, status=TaskStatus.PENDING)
    plan = AgentPlan(goal=AgentGoal(description="Meta"), tasks=[t1, t2])

    next_task = plan.get_next_pending_task()
    assert next_task is not None
    assert next_task.order == 2
    assert next_task.description == "Paso 2"


def test_8_waiting_confirmation_represents_execution_pause() -> None:
    t1 = AgentTask(
        description="Borrar registro antiguo", order=1, status=TaskStatus.WAITING_CONFIRMATION
    )
    plan = AgentPlan(goal=AgentGoal(description="Limpieza"), tasks=[t1])

    assert plan.is_waiting_confirmation() is True
    assert plan.is_completed() is False
    assert plan.get_next_pending_task() is None


def test_9_failed_task_retains_state() -> None:
    t1 = AgentTask(
        description="Operación fallida",
        order=1,
        status=TaskStatus.FAILED,
        error="Tool execution timeout",
    )
    plan = AgentPlan(goal=AgentGoal(description="Proceso"), tasks=[t1])

    assert plan.is_failed() is True
    assert t1.error == "Tool execution timeout"
    assert t1.status == TaskStatus.FAILED


def test_10_empty_plan_behavior() -> None:
    plan = AgentPlan(goal=AgentGoal(description="Meta vacía"), tasks=[])

    assert plan.get_next_pending_task() is None
    assert plan.is_completed() is False
    assert plan.is_failed() is False
    assert plan.is_waiting_confirmation() is False


def test_11_querying_plan_has_no_side_effects() -> None:
    t1 = AgentTask(description="Paso 1", order=1)
    plan = AgentPlan(goal=AgentGoal(description="Meta"), tasks=[t1])

    initial_snapshot = copy.deepcopy(plan)

    _ = plan.get_next_pending_task()
    _ = plan.is_completed()
    _ = plan.is_failed()
    _ = plan.is_waiting_confirmation()
    _ = plan.get_ordered_tasks()

    assert plan == initial_snapshot


def test_12_models_typing_and_no_external_dependencies() -> None:
    goal = AgentGoal(description="Prueba pura")
    task = AgentTask(description="Tarea pura", order=1, tool_name="TestTool")
    plan = AgentPlan(goal=goal, tasks=[task])

    assert isinstance(goal.goal_id, str)
    assert isinstance(task.task_id, str)
    assert isinstance(plan.plan_id, str)
    assert isinstance(task.status, TaskStatus)
    assert task.status.value == "PENDING"
