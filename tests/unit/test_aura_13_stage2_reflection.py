from __future__ import annotations

import pytest

from aura.cognition.reflection import (
    CognitiveReflector,
    ReflectionSeverity,
    ReflectionSummary,
)
from aura.cognition.verification import VerificationResult, VerificationStatus


@pytest.fixture
def reflector() -> CognitiveReflector:
    return CognitiveReflector()


def test_reflection_success(reflector: CognitiveReflector) -> None:
    ver = VerificationResult(
        status=VerificationStatus.SUCCESS,
        confidence=1.0,
        observations="Tool executed successfully with valid output.",
        suggested_action="CONTINUE",
    )
    res = reflector.reflect(ver)

    assert res.severity == ReflectionSeverity.INFO
    assert "No execution deviation detected" in res.root_cause
    assert res.recommended_action == "CONTINUE"
    assert res.confidence == 1.0
    assert len(res.hypotheses) > 0


def test_reflection_partial_success(reflector: CognitiveReflector) -> None:
    ver = VerificationResult(
        status=VerificationStatus.PARTIAL_SUCCESS,
        confidence=0.8,
        observations="Tool output does not explicitly confirm expected outcome 'json_payload'.",
        suggested_action="VERIFY",
        expected_outcome="json_payload",
        observed_outcome="raw_string_output",
    )
    res = reflector.reflect(ver)

    assert res.severity == ReflectionSeverity.WARNING
    assert "Partial execution deviation" in res.root_cause
    assert res.recommended_action == "VERIFY"
    assert 0.0 <= res.confidence <= 1.0
    assert "json_payload" in res.metadata.get("expected_outcome", "")


def test_reflection_transient_failure(reflector: CognitiveReflector) -> None:
    ver = VerificationResult(
        status=VerificationStatus.TRANSIENT_FAILURE,
        confidence=0.9,
        observations="Execution failed with transient error: 'Connection timeout'.",
        suggested_action="RETRY",
    )
    res = reflector.reflect(ver)

    assert res.severity == ReflectionSeverity.WARNING
    assert "Temporary operational failure" in res.root_cause
    assert res.recommended_action == "RETRY"
    assert res.confidence == 0.9
    assert any("timeout" in h.lower() or "network" in h.lower() for h in res.hypotheses)


def test_reflection_fatal_failure(reflector: CognitiveReflector) -> None:
    ver = VerificationResult(
        status=VerificationStatus.FATAL_FAILURE,
        confidence=0.95,
        observations="Execution failed with non-recoverable error: 'Permission denied'.",
        suggested_action="REPLAN",
    )
    res = reflector.reflect(ver)

    assert res.severity == ReflectionSeverity.CRITICAL
    assert "Non-recoverable execution failure" in res.root_cause
    assert res.recommended_action == "REPLAN"
    assert res.confidence == 0.95
    assert len(res.hypotheses) >= 2


def test_root_cause_transient_failure(reflector: CognitiveReflector) -> None:
    ver = VerificationResult(
        status=VerificationStatus.TRANSIENT_FAILURE,
        confidence=0.9,
        observations="Rate limit 429 exceeded",
        suggested_action="RETRY",
    )
    res = reflector.reflect(ver)

    assert "Temporary operational failure" in res.root_cause
    assert "Rate limit 429 exceeded" in res.root_cause


def test_root_cause_fatal_failure(reflector: CognitiveReflector) -> None:
    ver = VerificationResult(
        status=VerificationStatus.FATAL_FAILURE,
        confidence=0.95,
        observations="Syntax error in parameters",
        suggested_action="REPLAN",
    )
    res = reflector.reflect(ver)

    assert "Non-recoverable execution failure" in res.root_cause
    assert "Syntax error" in res.root_cause


def test_multiple_hypotheses_generated(reflector: CognitiveReflector) -> None:
    ver = VerificationResult(
        status=VerificationStatus.FATAL_FAILURE,
        confidence=0.9,
        observations="File not found /invalid/path",
        suggested_action="REPLAN",
    )
    res = reflector.reflect(ver)

    assert len(res.hypotheses) >= 3
    assert isinstance(res.hypotheses, list)


def test_observation_vs_hypothesis_distinction(reflector: CognitiveReflector) -> None:
    obs_text = "HTTP 503 Server Unavailable"
    ver = VerificationResult(
        status=VerificationStatus.TRANSIENT_FAILURE,
        confidence=0.9,
        observations=obs_text,
        suggested_action="RETRY",
    )
    res = reflector.reflect(ver)

    # Observation is literal evidence
    assert res.observations == obs_text
    # Hypotheses are candidate explanations distinct from raw observation
    assert res.observations not in res.hypotheses
    assert any(
        "overloaded" in h.lower() or "busy" in h.lower() or "network" in h.lower()
        for h in res.hypotheses
    )


def test_recommended_action_derivation(reflector: CognitiveReflector) -> None:
    ver1 = VerificationResult(
        status=VerificationStatus.SUCCESS,
        confidence=1.0,
        observations="OK",
        suggested_action="CONTINUE",
    )
    assert reflector.reflect(ver1).recommended_action == "CONTINUE"

    ver2 = VerificationResult(
        status=VerificationStatus.TRANSIENT_FAILURE,
        confidence=0.9,
        observations="Timeout",
        suggested_action="RETRY",
    )
    assert reflector.reflect(ver2).recommended_action == "RETRY"

    ver3 = VerificationResult(
        status=VerificationStatus.FATAL_FAILURE,
        confidence=0.95,
        observations="Fatal Error",
        suggested_action="ABORT",
    )
    assert reflector.reflect(ver3).recommended_action == "ABORT"


def test_confidence_validation_in_summary() -> None:
    summary1 = ReflectionSummary(
        severity=ReflectionSeverity.INFO,
        root_cause="None",
        hypotheses=[],
        observations="OK",
        lesson_learned="None",
        recommended_action="CONTINUE",
        confidence=1.8,  # High out of range
    )
    assert summary1.confidence == 1.0

    summary2 = ReflectionSummary(
        severity=ReflectionSeverity.INFO,
        root_cause="None",
        hypotheses=[],
        observations="OK",
        lesson_learned="None",
        recommended_action="CONTINUE",
        confidence=-0.4,  # Low out of range
    )
    assert summary2.confidence == 0.0


def test_reflection_determinism(reflector: CognitiveReflector) -> None:
    ver = VerificationResult(
        status=VerificationStatus.TRANSIENT_FAILURE,
        confidence=0.85,
        observations="Database lock timeout",
        suggested_action="RETRY",
    )

    res1 = reflector.reflect(ver)
    res2 = reflector.reflect(ver)

    assert res1.severity == res2.severity
    assert res1.root_cause == res2.root_cause
    assert res1.hypotheses == res2.hypotheses
    assert res1.observations == res2.observations
    assert res1.lesson_learned == res2.lesson_learned
    assert res1.recommended_action == res2.recommended_action
    assert res1.confidence == res2.confidence


def test_reflection_no_side_effects(reflector: CognitiveReflector) -> None:
    ver = VerificationResult(
        status=VerificationStatus.PARTIAL_SUCCESS,
        confidence=0.8,
        observations="Partial payload",
        suggested_action="VERIFY",
        metadata={"step_id": "step_123"},
    )
    original_meta = dict(ver.metadata)

    _ = reflector.reflect(ver)

    assert ver.metadata == original_meta
    assert ver.status == VerificationStatus.PARTIAL_SUCCESS


def test_metadata_preservation(reflector: CognitiveReflector) -> None:
    ver = VerificationResult(
        status=VerificationStatus.SUCCESS,
        confidence=1.0,
        observations="Task complete",
        suggested_action="CONTINUE",
        metadata={"tool": "calculator", "duration": 1.2},
    )
    res = reflector.reflect(ver)

    assert res.metadata["tool"] == "calculator"
    assert res.metadata["duration"] == 1.2


def test_incomplete_verification_result_handling(reflector: CognitiveReflector) -> None:
    ver = VerificationResult(
        status=VerificationStatus.FATAL_FAILURE,
        confidence=0.5,
        observations="",  # Empty observations
        suggested_action="",  # Empty suggested action
    )
    res = reflector.reflect(ver)

    assert res.severity == ReflectionSeverity.CRITICAL
    assert res.root_cause != ""
    assert res.recommended_action == "REPLAN"
    assert 0.0 <= res.confidence <= 1.0
