"""Manual demonstration script for AURA 1.0 Autonomous Multi-Step Agent Execution Flow.

This script simulates the complete flow:
  User Speech -> AgentGoal & AgentPlan -> AgentExecutor -> ToolRegistry -> Evaluation -> Output
"""

from __future__ import annotations

import sys

from aura.autonomy import (
    AgentExecutionResult,
    AgentExecutor,
    AgentGoal,
    AgentPlan,
    AgentTask,
)
from aura.cognition import TaskEvaluator
from aura.events import AgentStepEvaluated, EventBus, ToolConfirmationRequired
from aura.tools.builtins import CalculatorTool, DateTimeTool, SystemStatusTool
from aura.tools.registry import ToolRegistry


def main() -> int:
    print("==================================================================")
    print("          AURA 1.0 — AUTONOMOUS MULTI-STEP AGENT DEMO             ")
    print("==================================================================")

    # 1. Setup Infra (EventBus & ToolRegistry)
    event_bus = EventBus()
    registry = ToolRegistry()
    registry.register(DateTimeTool())
    registry.register(CalculatorTool())
    registry.register(SystemStatusTool())

    # Event Listeners
    def on_step_evaluated(evt: AgentStepEvaluated) -> None:
        print(f"  [EVENT AgentStepEvaluated] Task: {evt.task_id} -> {evt.evaluation_status}")

    def on_conf_required(evt: ToolConfirmationRequired) -> None:
        print(f"  [EVENT ToolConfirmationRequired] Tool: {evt.tool_name} (Risk: {evt.risk_level})")

    event_bus.subscribe(AgentStepEvaluated, on_step_evaluated)
    event_bus.subscribe(ToolConfirmationRequired, on_conf_required)

    # 2. Simulated User Input
    user_request = (
        "Revisar la hora actual, calcular el costo de 4 componentes de $150 "
        "y verificar el estado del sistema."
    )
    print(f'\n[ENTRADA DE USUARIO]: "{user_request}"')

    # 3. Create AgentGoal & AgentPlan
    goal = AgentGoal(description="Comprobación del sistema y cálculo de presupuesto")
    tasks = [
        AgentTask(
            description="Paso 1: Consultar hora actual",
            order=1,
            tool_name="datetime_tool",
            parameters={"action": "now"},
        ),
        AgentTask(
            description="Paso 2: Calcular 150 * 4",
            order=2,
            tool_name="calculator_tool",
            parameters={"expression": "150 * 4"},
        ),
        AgentTask(
            description="Paso 3: Diagnosticar salud del sistema",
            order=3,
            tool_name="system_status_tool",
            parameters={},
        ),
    ]
    plan = AgentPlan(goal=goal, tasks=tasks)
    print(f"\n[PLAN AGÉNTICO GENERADO] Plan ID: {plan.plan_id} (Goal: '{goal.description}')")

    # 4. Initialize AgentExecutor & TaskEvaluator
    evaluator = TaskEvaluator()
    executor = AgentExecutor(
        max_agent_steps=5, event_bus=event_bus, registry=registry, evaluator=evaluator
    )

    # 5. Execute Plan
    print("\n[INICIANDO BUCLE DE EJECUCIÓN AGÉNTICA MULTI-STEP...]")
    result: AgentExecutionResult = executor.execute_plan(plan)

    print("\n==================================================================")
    print("                     RESULTADO DE EJECUCIÓN                       ")
    print("==================================================================")
    print(f"Pasos ejecutados: {result.steps_executed}")
    print(f"Completado exitosamente: {result.completed}")
    print(f"Fallo en ejecución: {result.failed}")
    print(f"Pausado por confirmación: {result.waiting_confirmation}")

    print("\nDetalle de tareas ejecutadas:")
    for t in plan.get_ordered_tasks():
        print(f"  • Task {t.order} [{t.status.value}]: '{t.description}'")
        if t.result is not None:
            print(f"    -> Resultado: {t.result}")
        if t.error is not None:
            print(f"    -> Error: {t.error}")

    print("\n[VALIDACIÓN DEMO MANUAL COMPLETADA CON ÉXITO]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
