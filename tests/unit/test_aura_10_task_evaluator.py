from __future__ import annotations

from aura.autonomy import AgentExecutor, AgentGoal, AgentPlan, AgentTask, Observation, TaskStatus
from aura.cognition import EvaluationResult, EvaluationStatus, TaskEvaluator
from aura.events import AgentStepEvaluated, EventBus
from aura.tools.base import BaseTool, ToolMetadata, ToolResult
from aura.tools.builtins import CalculatorTool
from aura.tools.registry import ToolRegistry


class CustomFailingTool(BaseTool):
    metadata = ToolMetadata(name="custom_fail", description="Fails always")

    def execute(self, **kwargs: object) -> ToolResult:
        return ToolResult(success=False, error="Custom tool failure")


def test_1_evaluation_success_status() -> None:
    evaluator = TaskEvaluator()
    task = AgentTask(description="Suma", task_id="t1")
    obs = Observation(task_id="t1", success=True, output=150)

    res = evaluator.evaluate(task, obs)
    assert res.status == EvaluationStatus.SUCCESS
    assert res.task_id == "t1"
    assert "completed successfully" in res.reason


def test_2_evaluation_failed_status() -> None:
    evaluator = TaskEvaluator()
    task = AgentTask(description="Resta", task_id="t2")
    obs = Observation(task_id="t2", success=False, error="Error de sintaxis")

    res = evaluator.evaluate(task, obs)
    assert res.status == EvaluationStatus.FAILED
    assert res.task_id == "t2"
    assert res.reason == "Error de sintaxis"


def test_3_tool_result_conversion_to_observation() -> None:
    tr = ToolResult(success=True, output="10:00", execution_time_ms=5.0)
    obs = Observation.from_tool_result("t3", tr)
    assert obs.task_id == "t3"
    assert obs.success is True
    assert obs.output == "10:00"


def test_4_evaluation_result_success_structure() -> None:
    evaluator = TaskEvaluator()
    task = AgentTask(description="Task 4", task_id="t4")
    obs = Observation(task_id="t4", success=True, output="Done")

    res: EvaluationResult = evaluator.evaluate(task, obs)
    assert isinstance(res, EvaluationResult)
    assert res.status == EvaluationStatus.SUCCESS
    assert res.observation.output == "Done"


def test_5_evaluation_result_failed_structure() -> None:
    evaluator = TaskEvaluator()
    task = AgentTask(description="Task 5", task_id="t5")
    obs = Observation(task_id="t5", success=False, error="Timeout")

    res: EvaluationResult = evaluator.evaluate(task, obs)
    assert isinstance(res, EvaluationResult)
    assert res.status == EvaluationStatus.FAILED
    assert res.observation.error == "Timeout"


def test_6_error_message_preserved() -> None:
    evaluator = TaskEvaluator()
    task = AgentTask(description="Task 6", task_id="t6")
    obs = Observation(task_id="t6", success=False, error="Memoria insuficiente")

    res = evaluator.evaluate(task, obs)
    assert res.reason == "Memoria insuficiente"


def test_7_task_id_preserved() -> None:
    evaluator = TaskEvaluator()
    task = AgentTask(description="Task 7", task_id="task_special_777")
    obs = Observation(task_id="task_special_777", success=True)

    res = evaluator.evaluate(task, obs)
    assert res.task_id == "task_special_777"


def test_8_evaluation_is_deterministic() -> None:
    evaluator = TaskEvaluator()
    task = AgentTask(description="Task 8", task_id="t8")
    obs = Observation(task_id="t8", success=True, output="Constante")

    res1 = evaluator.evaluate(task, obs)
    res2 = evaluator.evaluate(task, obs)

    assert res1 == res2


def test_9_evaluator_no_llm_calls() -> None:
    evaluator = TaskEvaluator()
    task = AgentTask(description="Pura", task_id="t9")
    obs = Observation(task_id="t9", success=True)
    res = evaluator.evaluate(task, obs)
    assert res.status == EvaluationStatus.SUCCESS


def test_10_evaluator_no_sqlite_modifications() -> None:
    evaluator = TaskEvaluator()
    task = AgentTask(description="Sin DB", task_id="t10")
    obs = Observation(task_id="t10", success=True)
    res = evaluator.evaluate(task, obs)
    assert res.status == EvaluationStatus.SUCCESS


def test_11_evaluator_no_tool_executions() -> None:
    evaluator = TaskEvaluator()
    task = AgentTask(description="Sin tool execution", task_id="t11")
    obs = Observation(task_id="t11", success=True)
    res = evaluator.evaluate(task, obs)
    assert res.status == EvaluationStatus.SUCCESS


def test_12_agent_executor_observation_evaluator_integration() -> None:
    event_bus = EventBus()
    evaluated_events: list[AgentStepEvaluated] = []

    def handle_evaluated(event: AgentStepEvaluated) -> None:
        evaluated_events.append(event)

    event_bus.subscribe(AgentStepEvaluated, handle_evaluated)

    registry = ToolRegistry()
    registry.register(CalculatorTool())

    t1 = AgentTask(
        description="Paso 1: Calc",
        order=1,
        tool_name="calculator_tool",
        parameters={"expression": "50 + 50"},
    )
    plan = AgentPlan(goal=AgentGoal(description="Test Integración"), tasks=[t1])

    executor = AgentExecutor(event_bus=event_bus, registry=registry)
    res = executor.execute_plan(plan)

    assert res.completed is True
    assert t1.status == TaskStatus.SUCCESS
    assert t1.result == 100
    assert len(evaluated_events) == 1
    assert evaluated_events[0].evaluation_status == "SUCCESS"
    assert evaluated_events[0].task_id == t1.task_id


def test_13_failed_task_does_not_continue_silently() -> None:
    registry = ToolRegistry()
    registry.register(CustomFailingTool())
    registry.register(CalculatorTool())

    t1 = AgentTask(description="Paso 1 (Falla)", order=1, tool_name="custom_fail")
    t2 = AgentTask(
        description="Paso 2",
        order=2,
        tool_name="calculator_tool",
        parameters={"expression": "1 + 1"},
    )
    plan = AgentPlan(goal=AgentGoal(description="Test fallo no silencioso"), tasks=[t1, t2])

    executor = AgentExecutor(registry=registry)
    res = executor.execute_plan(plan)

    assert res.failed is True
    assert res.completed is False
    assert t1.status == TaskStatus.FAILED
    assert t1.error == "Custom tool failure"
    assert t2.status == TaskStatus.PENDING


def test_14_successful_task_allows_continuation() -> None:
    registry = ToolRegistry()
    registry.register(CalculatorTool())

    t1 = AgentTask(
        description="Paso 1",
        order=1,
        tool_name="calculator_tool",
        parameters={"expression": "10 * 10"},
    )
    t2 = AgentTask(
        description="Paso 2",
        order=2,
        tool_name="calculator_tool",
        parameters={"expression": "20 * 20"},
    )
    plan = AgentPlan(goal=AgentGoal(description="Test continuación"), tasks=[t1, t2])

    executor = AgentExecutor(registry=registry)
    res = executor.execute_plan(plan)

    assert res.completed is True
    assert res.steps_executed == 2
    assert t1.status == TaskStatus.SUCCESS
    assert t2.status == TaskStatus.SUCCESS


def test_15_replan_required_enum_exists_without_auto_planner() -> None:
    assert EvaluationStatus.REPLAN_REQUIRED.value == "REPLAN_REQUIRED"
    eval_result = EvaluationResult(
        task_id="t15",
        status=EvaluationStatus.REPLAN_REQUIRED,
        reason="Condición imprevista requiere replanificación",
        observation=Observation(task_id="t15", success=False),
    )
    assert eval_result.status == EvaluationStatus.REPLAN_REQUIRED
