from __future__ import annotations

import pytest

from aura.autonomy.agent_models import AgentTask, TaskStatus
from aura.cognition.verification import (
    ActionVerifier,
    VerificationResult,
    VerificationStatus,
)
from aura.tools.base import ToolResult


@pytest.fixture
def verifier() -> ActionVerifier:
    return ActionVerifier()


@pytest.fixture
def sample_task() -> AgentTask:
    return AgentTask(
        description="Search user preferences file",
        tool_name="file_search",
        parameters={"query": "user settings"},
        status=TaskStatus.IN_PROGRESS,
    )


def test_verification_successful_tool_result(
    verifier: ActionVerifier, sample_task: AgentTask
) -> None:
    tool_res = ToolResult(
        success=True, output={"status": "found", "count": 3}, execution_time_ms=12.5
    )
    result = verifier.verify(task=sample_task, tool_result=tool_res)

    assert result.status == VerificationStatus.SUCCESS
    assert result.confidence == 1.0
    assert result.suggested_action == "CONTINUE"
    assert "executed successfully" in result.observations


def test_verification_transient_failure(verifier: ActionVerifier, sample_task: AgentTask) -> None:
    tool_res = ToolResult(
        success=False, error="Connection timeout to remote service", execution_time_ms=5000.0
    )
    result = verifier.verify(task=sample_task, tool_result=tool_res)

    assert result.status == VerificationStatus.TRANSIENT_FAILURE
    assert 0.0 <= result.confidence <= 1.0
    assert result.suggested_action == "RETRY"
    assert "transient error" in result.observations.lower()


def test_verification_fatal_failure(verifier: ActionVerifier, sample_task: AgentTask) -> None:
    tool_res = ToolResult(
        success=False, error="Permission denied accessing /etc/shadow", execution_time_ms=2.0
    )
    result = verifier.verify(task=sample_task, tool_result=tool_res)

    assert result.status == VerificationStatus.FATAL_FAILURE
    assert 0.0 <= result.confidence <= 1.0
    assert result.suggested_action == "REPLAN"
    assert "non-recoverable error" in result.observations.lower()


def test_verification_partial_success_empty_output(
    verifier: ActionVerifier, sample_task: AgentTask
) -> None:
    tool_res = ToolResult(success=True, output={}, execution_time_ms=5.0)
    result = verifier.verify(task=sample_task, tool_result=tool_res)

    assert result.status == VerificationStatus.PARTIAL_SUCCESS
    assert 0.0 <= result.confidence <= 1.0
    assert result.suggested_action == "CONTINUE"
    assert "empty or incomplete" in result.observations.lower()


def test_verification_confidence_range_validation() -> None:
    res1 = VerificationResult(
        status=VerificationStatus.SUCCESS,
        confidence=1.5,  # Out of range (high)
        observations="Test high confidence",
        suggested_action="CONTINUE",
    )
    assert res1.confidence == 1.0

    res2 = VerificationResult(
        status=VerificationStatus.SUCCESS,
        confidence=-0.5,  # Out of range (low)
        observations="Test low confidence",
        suggested_action="CONTINUE",
    )
    assert res2.confidence == 0.0


def test_verification_observations_generated(
    verifier: ActionVerifier, sample_task: AgentTask
) -> None:
    tool_res = ToolResult(success=True, output="File saved successfully", execution_time_ms=10.0)
    result = verifier.verify(task=sample_task, tool_result=tool_res, expected_outcome="file saved")

    assert result.observations != ""
    assert "satisfies expected outcome" in result.observations
    assert result.expected_outcome == "file saved"


def test_verification_suggested_action_determination(
    verifier: ActionVerifier, sample_task: AgentTask
) -> None:
    # Expected outcome unmet
    tool_res = ToolResult(success=True, output="Unknown data format", execution_time_ms=15.0)
    result = verifier.verify(task=sample_task, tool_result=tool_res, expected_outcome="JSON report")

    assert result.status == VerificationStatus.PARTIAL_SUCCESS
    assert result.suggested_action == "VERIFY"


def test_verification_missing_data_ambiguous(
    verifier: ActionVerifier, sample_task: AgentTask
) -> None:
    result = verifier.verify(task=sample_task, tool_result=None)

    assert result.status == VerificationStatus.FATAL_FAILURE
    assert result.confidence == 1.0
    assert result.suggested_action == "ABORT"
    assert "no execution result" in result.observations.lower()


def test_verification_no_side_effects(verifier: ActionVerifier, sample_task: AgentTask) -> None:
    original_task_status = sample_task.status
    tool_res = ToolResult(success=True, output="Done", execution_time_ms=1.0)

    _ = verifier.verify(task=sample_task, tool_result=tool_res)

    assert sample_task.status == original_task_status
    assert sample_task.result is None
    assert sample_task.error is None


def test_verification_determinism(verifier: ActionVerifier, sample_task: AgentTask) -> None:
    tool_res = ToolResult(success=True, output={"data": 42}, execution_time_ms=8.0)

    res1 = verifier.verify(task=sample_task, tool_result=tool_res, expected_outcome="data")
    res2 = verifier.verify(task=sample_task, tool_result=tool_res, expected_outcome="data")

    assert res1.status == res2.status
    assert res1.confidence == res2.confidence
    assert res1.observations == res2.observations
    assert res1.suggested_action == res2.suggested_action
