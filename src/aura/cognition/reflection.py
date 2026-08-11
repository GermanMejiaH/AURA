from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .verification import VerificationResult, VerificationStatus


class ReflectionSeverity(str, Enum):
    """Severity level of a cognitive reflection summary."""

    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass
class ReflectionSummary:
    """Encapsulates a structured cognitive reflection and root cause diagnosis."""

    severity: ReflectionSeverity
    root_cause: str
    hypotheses: list[str]
    observations: str
    lesson_learned: str
    recommended_action: str
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Ensures confidence is explicitly validated and clamped to [0.0, 1.0]."""
        if not isinstance(self.confidence, (int, float)):
            try:
                self.confidence = float(self.confidence)
            except ValueError, TypeError:
                self.confidence = 0.0
        self.confidence = max(0.0, min(1.0, float(self.confidence)))


class CognitiveReflector:
    """Transforms a VerificationResult into a structured cognitive reflection."""

    def reflect(self, verification: VerificationResult) -> ReflectionSummary:
        """Analyzes a VerificationResult and produces a deterministic ReflectionSummary.

        Args:
            verification: The VerificationResult to reflect upon.

        Returns:
            ReflectionSummary containing root cause, hypotheses, lesson, and recommended action.
        """
        obs = verification.observations or "No specific observations recorded."
        exp = verification.expected_outcome
        actual = verification.observed_outcome

        # Preserve metadata from verification
        ref_metadata = dict(verification.metadata)
        if exp:
            ref_metadata["expected_outcome"] = exp
        if actual:
            ref_metadata["observed_outcome"] = actual

        # 1. SUCCESS
        if verification.status == VerificationStatus.SUCCESS:
            return ReflectionSummary(
                severity=ReflectionSeverity.INFO,
                root_cause="No execution deviation detected; action completed successfully.",
                hypotheses=["Strategy executed as expected without obstacles."],
                observations=obs,
                lesson_learned=(
                    "Strategy produced expected outcome; pattern is effective for this step type."
                ),
                recommended_action="CONTINUE",
                confidence=verification.confidence,
                metadata=ref_metadata,
            )

        # 2. PARTIAL_SUCCESS
        if verification.status == VerificationStatus.PARTIAL_SUCCESS:
            hypotheses = [
                "Tool executed but returned incomplete or empty output payload.",
                "Expected postcondition tokens were not fully confirmed in tool output.",
            ]
            root_cause = f"Partial execution deviation: {obs}"

            rec_action = verification.suggested_action
            if rec_action not in ("CONTINUE", "VERIFY", "RETRY", "REPLAN", "ABORT"):
                rec_action = "VERIFY"

            lesson = (
                f"Action completed with partial results ({obs}); "
                "verification or parameter adjustment recommended."
            )

            # Confidence scaled slightly to reflect partial uncertainty
            conf = max(0.5, min(1.0, verification.confidence * 0.9))

            return ReflectionSummary(
                severity=ReflectionSeverity.WARNING,
                root_cause=root_cause,
                hypotheses=hypotheses,
                observations=obs,
                lesson_learned=lesson,
                recommended_action=rec_action,
                confidence=conf,
                metadata=ref_metadata,
            )

        # 3. TRANSIENT_FAILURE
        if verification.status == VerificationStatus.TRANSIENT_FAILURE:
            hypotheses = [
                "Network connection or API service temporarily unavailable.",
                "Resource busy or request rate-limited by remote host.",
                "Execution timeout exceeded standard interval.",
            ]
            root_cause = f"Temporary operational failure: {obs}"

            rec_action = verification.suggested_action
            if rec_action not in ("RETRY", "REPLAN", "ABORT"):
                rec_action = "RETRY"

            lesson = (
                f"Failure appears transient ({obs}); retry is appropriate before strategy revision."
            )

            return ReflectionSummary(
                severity=ReflectionSeverity.WARNING,
                root_cause=root_cause,
                hypotheses=hypotheses,
                observations=obs,
                lesson_learned=lesson,
                recommended_action=rec_action,
                confidence=verification.confidence,
                metadata=ref_metadata,
            )

        # 4. FATAL_FAILURE (or unclassified failure)
        hypotheses = [
            "Action parameters or preconditions were invalid.",
            "Required resource, file, or permission for action is unavailable.",
            "Strategy cannot proceed without replanning or task abort.",
        ]
        root_cause = f"Non-recoverable execution failure: {obs}"

        rec_action = verification.suggested_action
        if rec_action not in ("REPLAN", "ABORT"):
            rec_action = "REPLAN"

        lesson = (
            f"Action cannot succeed with current parameters/strategy ({obs}); "
            "structural replanning or abort required."
        )

        return ReflectionSummary(
            severity=ReflectionSeverity.CRITICAL,
            root_cause=root_cause,
            hypotheses=hypotheses,
            observations=obs,
            lesson_learned=lesson,
            recommended_action=rec_action,
            confidence=verification.confidence,
            metadata=ref_metadata,
        )
