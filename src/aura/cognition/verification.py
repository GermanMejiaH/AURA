from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..autonomy.agent_models import AgentTask
    from ..tools.base import ToolResult


class VerificationStatus(str, Enum):
    """Execution verification status for actions and tool steps."""

    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    TRANSIENT_FAILURE = "TRANSIENT_FAILURE"
    FATAL_FAILURE = "FATAL_FAILURE"


@dataclass
class VerificationResult:
    """Encapsulates the deterministic verification result of an executed action or tool step."""

    status: VerificationStatus
    confidence: float
    observations: str
    suggested_action: str
    expected_outcome: str | None = None
    observed_outcome: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Ensures confidence is explicitly validated and clamped to [0.0, 1.0]."""
        if not isinstance(self.confidence, (int, float)):
            try:
                self.confidence = float(self.confidence)
            except ValueError, TypeError:
                self.confidence = 0.0
        self.confidence = max(0.0, min(1.0, float(self.confidence)))


class ActionVerifier:
    """Evaluates action and tool execution outcomes deterministically without LLM calls."""

    TRANSIENT_ERROR_PATTERNS: tuple[str, ...] = (
        "timeout",
        "timed out",
        "rate limit",
        "connection",
        "busy",
        "temporary",
        "transient",
        "retry",
        "network",
        "server error",
        "503",
        "504",
        "429",
        "econnreset",
        "etimedout",
        "lock",
        "unavailable",
    )

    FATAL_ERROR_PATTERNS: tuple[str, ...] = (
        "permission denied",
        "unauthorized",
        "access denied",
        "invalid parameter",
        "syntax error",
        "not found",
        "keyerror",
        "typeerror",
        "valueerror",
        "not implemented",
    )

    def verify(
        self,
        task: AgentTask,
        tool_result: ToolResult | None = None,
        expected_outcome: str | None = None,
    ) -> VerificationResult:
        """Deterministically evaluates the task execution outcome against expected postconditions.

        Args:
            task: The AgentTask being evaluated.
            tool_result: Optional ToolResult produced by tool execution.
            expected_outcome: Optional explicit expected postcondition description.

        Returns:
            VerificationResult detailing status, confidence, observations, and suggested action.
        """
        # Determine effective expected outcome
        eff_expected = expected_outcome
        if not eff_expected and hasattr(task, "parameters") and isinstance(task.parameters, dict):
            eff_expected = task.parameters.get("expected_outcome") or task.parameters.get(
                "expected"
            )

        # 1. Check if no result was provided at all
        if tool_result is None and task.result is None and task.error is None:
            desc = task.description
            return VerificationResult(
                status=VerificationStatus.FATAL_FAILURE,
                confidence=1.0,
                observations=f"No execution result or output provided for task '{desc}'.",
                suggested_action="ABORT",
                expected_outcome=eff_expected,
                observed_outcome=None,
            )

        # Extract explicit error message if present
        error_msg: str | None = None
        if tool_result and not tool_result.success:
            error_msg = tool_result.error or "Tool execution failed without error message."
        elif task.error:
            error_msg = task.error

        # 2. Handle failure cases
        if error_msg is not None:
            err_lower = error_msg.lower()
            observed_str = f"Error: {error_msg}"

            # Check transient vs fatal patterns
            is_transient = any(pat in err_lower for pat in self.TRANSIENT_ERROR_PATTERNS)
            if (
                not is_transient
                and tool_result
                and hasattr(tool_result, "output")
                and isinstance(tool_result.output, dict)
            ):
                is_transient = bool(
                    tool_result.output.get("transient") or tool_result.output.get("recoverable")
                )

            if is_transient:
                return VerificationResult(
                    status=VerificationStatus.TRANSIENT_FAILURE,
                    confidence=0.9,
                    observations=f"Execution failed with transient error: '{error_msg}'.",
                    suggested_action="RETRY",
                    expected_outcome=eff_expected,
                    observed_outcome=observed_str,
                )

            return VerificationResult(
                status=VerificationStatus.FATAL_FAILURE,
                confidence=0.95,
                observations=f"Execution failed with non-recoverable error: '{error_msg}'.",
                suggested_action="REPLAN",
                expected_outcome=eff_expected,
                observed_outcome=observed_str,
            )

        # 3. Successful execution cases
        observed_output = tool_result.output if tool_result is not None else task.result
        observed_str = str(observed_output) if observed_output is not None else "None"

        # Check for empty or partial output
        is_empty = (
            observed_output is None
            or observed_output == ""
            or observed_output == {}
            or observed_output == []
        )
        is_partial = False
        if isinstance(observed_output, dict):
            is_partial = bool(observed_output.get("partial") or observed_output.get("incomplete"))

        if is_empty or is_partial:
            return VerificationResult(
                status=VerificationStatus.PARTIAL_SUCCESS,
                confidence=0.8,
                observations="Tool executed successfully but returned empty or incomplete output.",
                suggested_action="CONTINUE",
                expected_outcome=eff_expected,
                observed_outcome=observed_str,
            )

        # Check expected outcome matching if provided
        if eff_expected:
            exp_tokens = set(eff_expected.lower().split())
            obs_lower = observed_str.lower()
            matched = [tok for tok in exp_tokens if tok in obs_lower]

            if matched:
                return VerificationResult(
                    status=VerificationStatus.SUCCESS,
                    confidence=1.0,
                    observations=f"Tool output satisfies expected outcome '{eff_expected}'.",
                    suggested_action="CONTINUE",
                    expected_outcome=eff_expected,
                    observed_outcome=observed_str,
                )

            return VerificationResult(
                status=VerificationStatus.PARTIAL_SUCCESS,
                confidence=0.7,
                observations=(
                    f"Tool output does not explicitly confirm expected outcome '{eff_expected}'."
                ),
                suggested_action="VERIFY",
                expected_outcome=eff_expected,
                observed_outcome=observed_str,
            )

        # Standard successful verification
        return VerificationResult(
            status=VerificationStatus.SUCCESS,
            confidence=1.0,
            observations=f"Task '{task.description}' executed successfully with valid output.",
            suggested_action="CONTINUE",
            expected_outcome=eff_expected,
            observed_outcome=observed_str,
        )
