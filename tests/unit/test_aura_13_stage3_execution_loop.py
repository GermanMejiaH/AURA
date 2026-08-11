from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from aura.autonomy.agent_models import AgentGoal, AgentPlan, AgentTask, TaskStatus
from aura.autonomy.executor import AgentExecutor
from aura.autonomy.replanner import AgentReplanner
from aura.cognition.evaluator import EvaluationResult, EvaluationStatus
from aura.cognition.provider import LLMProvider
from aura.cognition.reflection import CognitiveReflector, ReflectionSeverity, ReflectionSummary
from aura.cognition.verification import ActionVerifier, VerificationResult, VerificationStatus
from aura.container import DependencyContainer
from aura.tools.base import BaseTool, ToolMetadata, ToolResult
from aura.tools.registry import ToolRegistry


class DummySuccessTool(BaseTool):
    def __init__(self) -> None:
        self.metadata = ToolMetadata(
            name="dummy_success",
            description="Returns successful output",
        )

    def execute(self, **kwargs: Any) -> ToolResult:
        return ToolResult(success=True, output="Executed successfully")


class DummyTransientFailTool(BaseTool):
    def __init__(self) -> None:
        self.metadata = ToolMetadata(
            name="dummy_transient",
            description="Fails with transient error",
        )

    def execute(self, **kwargs: Any) -> ToolResult:
        return ToolResult(success=False, error="Connection timeout")


class DummyFatalFailTool(BaseTool):
    def __init__(self) -> None:
        self.metadata = ToolMetadata(
            name="dummy_fatal",
            description="Fails with fatal error",
        )

    def execute(self, **kwargs: Any) -> ToolResult:
        return ToolResult(success=False, error="Invalid parameters")


@pytest.fixture
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(DummySuccessTool())
    reg.register(DummyTransientFailTool())
    reg.register(DummyFatalFailTool())
    return reg


@pytest.fixture
def plan() -> AgentPlan:
    goal = AgentGoal(description="Test execution loop")
    p = AgentPlan(goal=goal, plan_id="plan_stage3_test")
    p.tasks = [
        AgentTask(
            task_id="task_1",
            description="Execute dummy tool",
            order=1,
            tool_name="dummy_success",
            parameters={},
        )
    ]
    return p


def test_action_success_flow(registry: ToolRegistry, plan: AgentPlan) -> None:
    executor = AgentExecutor(registry=registry)
    res = executor.execute_plan(plan)

    assert res.completed is True
    assert res.failed is False
    assert plan.tasks[0].status == TaskStatus.SUCCESS
    assert plan.tasks[0].result == "Executed successfully"


def test_partial_success_handling(registry: ToolRegistry) -> None:
    class DummyPartialTool(BaseTool):
        def __init__(self) -> None:
            self.metadata = ToolMetadata(
                name="dummy_partial",
                description="Returns raw string when JSON requested",
            )

        def execute(self, **kwargs: Any) -> ToolResult:
            return ToolResult(
                tool_name="dummy_partial",
                success=True,
                output="raw text output instead of json",
            )

    registry.register(DummyPartialTool())
    goal = AgentGoal(description="Test partial success")
    p = AgentPlan(goal=goal, plan_id="plan_partial")
    p.tasks = [
        AgentTask(
            task_id="task_p",
            description="Execute partial tool",
            order=1,
            tool_name="dummy_partial",
            parameters={"expected_outcome": "json_structure"},
        )
    ]

    mock_verifier = MagicMock(spec=ActionVerifier)
    mock_verifier.verify.return_value = VerificationResult(
        status=VerificationStatus.PARTIAL_SUCCESS,
        confidence=0.7,
        observations="Output is raw string, not json_structure",
        suggested_action="VERIFY",
    )

    mock_reflector = MagicMock(spec=CognitiveReflector)
    mock_reflector.reflect.return_value = ReflectionSummary(
        severity=ReflectionSeverity.WARNING,
        root_cause="Partial output mismatch",
        hypotheses=["Incompatible output format"],
        observations="Output is raw string, not json_structure",
        lesson_learned="Check output format",
        recommended_action="VERIFY",
        confidence=0.7,
    )

    executor = AgentExecutor(registry=registry, verifier=mock_verifier, reflector=mock_reflector)
    _ = executor.execute_plan(p)

    # Should not mark automatically as completed without proper handling
    assert mock_verifier.verify.called
    assert mock_reflector.reflect.called


def test_transient_failure_controlled_retry(registry: ToolRegistry) -> None:
    goal = AgentGoal(description="Test retry")
    p = AgentPlan(goal=goal, plan_id="plan_retry")
    p.tasks = [
        AgentTask(
            task_id="task_retry",
            description="Execute transient fail tool",
            order=1,
            tool_name="dummy_transient",
            parameters={"_max_retries": 1},
        )
    ]

    executor = AgentExecutor(registry=registry)
    _ = executor.execute_plan(p)

    # Retry should have been attempted once and retry_count updated
    assert p.tasks[0].parameters.get("_retry_count") == 1


def test_transient_failure_exhausted_retries_triggers_replan(registry: ToolRegistry) -> None:
    goal = AgentGoal(description="Test exhausted retry")
    p = AgentPlan(goal=goal, plan_id="plan_exhausted")
    p.tasks = [
        AgentTask(
            task_id="task_exhausted",
            description="Execute transient fail tool",
            order=1,
            tool_name="dummy_transient",
            parameters={"_retry_count": 1, "_max_retries": 1},
        )
    ]

    mock_replanner = MagicMock(spec=AgentReplanner)
    mock_replanner.replan.return_value = False

    executor = AgentExecutor(registry=registry, replanner=mock_replanner)
    res = executor.execute_plan(p)

    assert mock_replanner.replan.called
    assert res.failed is True


def test_fatal_failure_no_blind_retry(registry: ToolRegistry) -> None:
    goal = AgentGoal(description="Test fatal failure")
    p = AgentPlan(goal=goal, plan_id="plan_fatal")
    p.tasks = [
        AgentTask(
            task_id="task_fatal",
            description="Execute fatal tool",
            order=1,
            tool_name="dummy_fatal",
            parameters={},
        )
    ]

    mock_replanner = MagicMock(spec=AgentReplanner)
    mock_replanner.replan.return_value = False

    executor = AgentExecutor(registry=registry, replanner=mock_replanner)
    res = executor.execute_plan(p)

    # Should call replanner directly without retrying
    assert mock_replanner.replan.called
    assert p.tasks[0].parameters.get("_retry_count") is None
    assert res.failed is True


def test_reflection_summary_passed_to_replanner(registry: ToolRegistry) -> None:
    goal = AgentGoal(description="Test reflection passing")
    p = AgentPlan(goal=goal, plan_id="plan_reflection_pass")
    p.tasks = [
        AgentTask(
            task_id="task_fail",
            description="Execute fatal tool",
            order=1,
            tool_name="dummy_fatal",
            parameters={},
        )
    ]

    mock_replanner = MagicMock(spec=AgentReplanner)
    mock_replanner.replan.return_value = False

    executor = AgentExecutor(registry=registry, replanner=mock_replanner)
    executor.execute_plan(p)

    assert mock_replanner.replan.called
    _, kwargs = mock_replanner.replan.call_args
    assert "reflection" in kwargs
    ref = kwargs["reflection"]
    assert isinstance(ref, ReflectionSummary)
    assert "Permission denied" in ref.root_cause or "non-recoverable" in ref.root_cause.lower()
    assert len(ref.hypotheses) > 0


def test_root_cause_and_hypotheses_in_replanner_prompt() -> None:
    mock_llm = MagicMock(spec=LLMProvider)
    mock_llm.structured_reason.return_value = {"tasks": []}

    replanner = AgentReplanner(llm_provider=mock_llm)
    p = AgentPlan(goal=AgentGoal(description="Goal"), plan_id="p1")
    t = AgentTask(task_id="t1", description="Failed task", order=1, tool_name="tool1")
    obs = MagicMock()
    obs.error = "Error"
    eval_res = EvaluationResult(
        task_id="t1",
        status=EvaluationStatus.REPLAN_REQUIRED,
        reason="Failed",
        observation=obs,
    )

    ref = ReflectionSummary(
        severity=ReflectionSeverity.CRITICAL,
        root_cause="Access Denied to resource",
        hypotheses=["API token expired", "Insufficient permissions"],
        observations="HTTP 403 Forbidden",
        lesson_learned="Verify auth tokens before call",
        recommended_action="REPLAN",
        confidence=0.9,
    )

    replanner.replan(p, t, obs, eval_res, reflection=ref)

    assert mock_llm.structured_reason.called
    prompt = mock_llm.structured_reason.call_args[0][0]
    assert "Access Denied to resource" in prompt
    assert "API token expired" in prompt
    assert "Insufficient permissions" in prompt


def test_replanner_fallback_without_reflection() -> None:
    mock_llm = MagicMock(spec=LLMProvider)
    mock_llm.structured_reason.return_value = {"tasks": []}

    replanner = AgentReplanner(llm_provider=mock_llm)
    p = AgentPlan(goal=AgentGoal(description="Goal"), plan_id="p1")
    t = AgentTask(task_id="t1", description="Failed task", order=1, tool_name="tool1")
    obs = MagicMock()
    obs.error = "Generic Error"
    eval_res = EvaluationResult(
        task_id="t1",
        status=EvaluationStatus.REPLAN_REQUIRED,
        reason="Failed",
        observation=obs,
    )

    replanner.replan(p, t, obs, eval_res, reflection=None)

    assert mock_llm.structured_reason.called
    prompt = mock_llm.structured_reason.call_args[0][0]
    assert "COGNITIVE REFLECTION" not in prompt
    assert "Generic Error" in prompt


def test_ioc_container_resolves_verifier_and_reflector() -> None:
    container = DependencyContainer()
    verifier_inst = ActionVerifier()
    reflector_inst = CognitiveReflector()

    container.register(ActionVerifier, instance=verifier_inst)
    container.register(CognitiveReflector, instance=reflector_inst)

    resolved_v = container.resolve(ActionVerifier)
    resolved_r = container.resolve(CognitiveReflector)

    assert resolved_v is verifier_inst
    assert resolved_r is reflector_inst


def test_executor_uses_injected_components() -> None:
    v = ActionVerifier()
    r = CognitiveReflector()
    executor = AgentExecutor(verifier=v, reflector=r)

    assert executor.verifier is v
    assert executor.reflector is r


def test_infinite_loop_prevention_on_replan(registry: ToolRegistry) -> None:
    mock_llm = MagicMock(spec=LLMProvider)
    # Propose identical task to the failed task
    mock_llm.structured_reason.return_value = {
        "tasks": [
            {
                "description": "Execute fatal tool",
                "tool_name": "dummy_fatal",
                "parameters": {},
            }
        ]
    }

    replanner = AgentReplanner(llm_provider=mock_llm)
    p = AgentPlan(goal=AgentGoal(description="Goal"), plan_id="p1")
    t = AgentTask(task_id="t1", description="Failed task", order=1, tool_name="dummy_fatal")
    obs = MagicMock()
    eval_res = EvaluationResult(
        task_id="t1",
        status=EvaluationStatus.REPLAN_REQUIRED,
        reason="Failed",
        observation=obs,
    )

    success = replanner.replan(p, t, obs, eval_res, registry=registry)

    # Replan should be rejected to prevent infinite loop
    assert success is False
