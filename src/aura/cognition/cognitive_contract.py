"""Stage 21 — Strongly Typed Cognitive Contract.

Defines immutable data representations for LLM cognitive turn interpretations,
tool proposals, and response modes, ensuring cognitive outputs are treated
as untrusted proposal data prior to Stage 16 closed-loop execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CognitiveMode(Enum):
    """Enumeration of valid cognitive turn interpretation response modes."""

    DIRECT_RESPONSE = "direct_response"
    TOOL_PROPOSAL = "tool_proposal"
    CLARIFICATION_REQUIRED = "clarification_required"
    UNSUPPORTED = "unsupported"
    PROVIDER_ERROR = "provider_error"


@dataclass(frozen=True)
class ToolCallProposal:
    """Immutable representation of a proposed tool invocation."""

    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CognitiveTurnInterpretation:
    """Immutable representation of an LLM provider's cognitive interpretation of a user turn."""

    mode: CognitiveMode
    direct_response: str | None = None
    tool_proposal: ToolCallProposal | None = None
    reasoning: str | None = None
    confidence: float = 1.0
    error_message: str | None = None

    def __post_init__(self) -> None:
        # Sanitize tool proposal name if present
        if self.tool_proposal is not None and isinstance(self.tool_proposal.tool_name, str):
            object.__setattr__(
                self,
                "tool_proposal",
                ToolCallProposal(
                    tool_name=self.tool_proposal.tool_name.strip().lower(),
                    arguments=self.tool_proposal.arguments or {},
                ),
            )
